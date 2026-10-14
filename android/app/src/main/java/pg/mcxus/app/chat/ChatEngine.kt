package pg.mcxus.app.chat

import android.content.Context
import android.util.Base64
import android.util.Log
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject
import pg.mcxus.app.net.Api
import pg.mcxus.app.net.ApiError
import uniffi.mcxus_crypto.MlsClient
import java.io.File
import java.security.SecureRandom
import java.time.OffsetDateTime

data class Peer(val id: String, val name: String, val badge: String, val rating: String?, val reviews: Int)

data class Conversation(
    val id: String,
    val peer: Peer,
    val listingId: String?,
    val encryptionReady: Boolean,
    val startedByMe: Boolean,
    val lastPreview: String,
    val lastAt: Long,
    val unread: Int,
)

/** Result of getting a chat ready for encrypted messages. */
sealed class Readiness {
    data object Ready : Readiness()
    data class Waiting(val why: String) : Readiness()
    data class Failed(val why: String) : Readiness()
}

/**
 * End-to-end encrypted chat on this phone (ADR 0008).
 *
 * - Keys and group state live in an OpenMLS state file in app-private storage (filesDir/mls-<user>.bin).
 * - The server only relays ciphertext. Starting a chat claims one of the other person's one-time KeyPackages,
 *   creates an MLS group and uploads the Welcome. The first Welcome wins; a phone that loses the race waits.
 * - A long-poll loop (/v1/messages/sync?wait=25) delivers new messages within about a second without push.
 * - Decrypted messages are kept only in [ChatStore].
 */
class ChatEngine private constructor(
    private val api: Api,
    val userId: String,
    private val store: ChatStore,
    private val mls: MlsClient,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val lock = Mutex()
    private var loop: Job? = null
    private var deviceId: String = ""

    /** Bumped whenever messages or chats change, so screens re-read the store. */
    private val _version = MutableStateFlow(0L)
    val version: StateFlow<Long> = _version

    private val _conversations = MutableStateFlow<List<Conversation>>(emptyList())
    val conversations: StateFlow<List<Conversation>> = _conversations

    private val _online = MutableStateFlow(false)
    val online: StateFlow<Boolean> = _online

    private var serverConversations: List<JSONObject> = emptyList()

    fun start() {
        if (loop?.isActive == true) return
        loop = scope.launch {
            while (isActive) {
                try {
                    setUp()
                    syncForever()
                } catch (e: CancellationException) {
                    throw e
                } catch (e: ApiError) {
                    Log.w(TAG, "chat: ${e.code} ${e.message}")
                    _online.value = false
                    if (e.status == 401) return@launch // signed out elsewhere; the UI handles sign-in
                    delay(5_000)
                } catch (e: Exception) {
                    Log.w(TAG, "chat offline: ${e.message}")
                    _online.value = false
                    delay(5_000)
                }
            }
        }
    }

    fun stop() {
        scope.cancel()
        store.close()
    }

    private suspend fun setUp() {
        deviceId = store.get("device_id") ?: api.post("/v1/devices", JSONObject().put("name", android.os.Build.MODEL ?: "Android"))
            .getString("device_id").also { store.put("device_id", it) }
        topUpKeyPackages()
        refreshConversations()
        _online.value = true
    }

    /** Keep at least 10 unused KeyPackages on the server so people can start chats while this phone is offline. */
    private suspend fun topUpKeyPackages() {
        val unclaimed = api.obj("/v1/keys/count?device_id=$deviceId").getInt("unclaimed")
        if (unclaimed >= MIN_KEY_PACKAGES) return
        val packages = withContext(Dispatchers.IO) { mls.keyPackages(UPLOAD_KEY_PACKAGES.toUInt()) }
        val body = JSONObject().put("device_id", deviceId).put("key_packages", org.json.JSONArray(packages.map { b64(it) }))
        api.post("/v1/keys", body)
    }

    suspend fun refreshConversations() {
        val arr = api.list("/v1/conversations")
        serverConversations = (0 until arr.length()).map { arr.getJSONObject(it) }
        publish()
    }

    private fun publish() {
        val summaries = store.summaries()
        _conversations.value = serverConversations.map { c ->
            val id = c.getString("id")
            val s = summaries[id]
            val p = c.getJSONObject("peer")
            Conversation(
                id = id,
                peer = Peer(
                    p.getString("id"), p.getString("name"), p.optString("badge"),
                    if (p.isNull("rating")) null else p.getString("rating"), p.optInt("reviews"),
                ),
                listingId = if (c.isNull("listing_id")) null else c.getString("listing_id"),
                encryptionReady = c.getBoolean("encryption_ready"),
                startedByMe = c.getBoolean("started_by_me"),
                lastPreview = s?.let { Payload.preview(it.first) } ?: "Tap to start an encrypted chat",
                lastAt = s?.second ?: parseTime(c.optString("created_at")),
                unread = s?.third ?: 0,
            )
        }.sortedByDescending { it.lastAt }
        _version.value++
    }

    private suspend fun syncForever() {
        var cursor = store.get("cursor")?.toLong() ?: 0L
        while (true) {
            val batch = api.list("/v1/messages/sync?after=$cursor&limit=200&wait=25")
            _online.value = true
            if (batch.length() == 0) continue
            var unknownChat = false
            var gotWelcome = false
            lock.withLock {
                for (i in 0 until batch.length()) {
                    val m = batch.getJSONObject(i)
                    val conv = m.getString("conversation_id")
                    if (serverConversations.none { it.getString("id") == conv }) unknownChat = true
                    if (m.getString("kind") == "welcome") gotWelcome = true
                    handle(m, conv)
                    cursor = m.getLong("id")
                    store.put("cursor", cursor.toString())
                }
            }
            if (unknownChat) refreshConversations() else publish()
            if (gotWelcome) topUpKeyPackages()
        }
    }

    private fun handle(m: JSONObject, conv: String) {
        val payload = Base64.decode(m.getString("payload"), Base64.NO_WRAP)
        val at = parseTime(m.getString("created_at"))
        when (m.getString("kind")) {
            "welcome" -> if (group(conv) == null) {
                try {
                    store.put("group:$conv", hex(mls.join(payload)))
                } catch (e: Exception) {
                    Log.w(TAG, "join failed", e)
                    store.add(conv, null, false, Payload.system("Could not open this encrypted chat on this phone."), at, false)
                }
            }
            else -> {
                if (m.getString("sender_device_id") == deviceId) return // my own message: already stored when sent
                val gid = group(conv)
                if (gid == null) {
                    store.add(conv, m.getLong("id"), false, Payload.system("A message could not be decrypted (no keys)."), at, false)
                    return
                }
                try {
                    val d = mls.decrypt(gid, payload)
                    val text = d.plaintext ?: return // commits only change the group
                    val claimed = "user:" + m.getString("sender_user_id")
                    val body = if (d.sender == claimed) {
                        String(text, Charsets.UTF_8)
                    } else {
                        Payload.system("Warning: a message failed the sender check and was hidden.")
                    }
                    val mine = m.getString("sender_user_id") == userId
                    store.add(conv, m.getLong("id"), mine, body, at, !mine)
                } catch (e: Exception) {
                    Log.w(TAG, "decrypt failed", e)
                    store.add(conv, m.getLong("id"), false, Payload.system("A message could not be decrypted."), at, false)
                }
            }
        }
    }

    private fun group(conv: String): ByteArray? = store.get("group:$conv")?.let(::unhex)

    /** Open (or find) the one-to-one chat with [peerId]; optionally linked to a listing. */
    suspend fun open(peerId: String, listingId: String? = null): String {
        val body = JSONObject().put("peer_user_id", peerId)
        if (listingId != null) body.put("listing_id", listingId)
        val conv = api.post("/v1/conversations", body)
        refreshConversations()
        return conv.getString("id")
    }

    /** Make sure this phone can encrypt for [conversationId]; sets the chat up the first time. */
    suspend fun ensureReady(conversationId: String): Readiness = lock.withLock {
        if (group(conversationId) != null) return@withLock Readiness.Ready
        val conv = conversation(conversationId) ?: return@withLock Readiness.Failed("Chat not found")
        val fresh = api.post("/v1/conversations", JSONObject().put("peer_user_id", conv.peer.id))
        when {
            !fresh.getBoolean("encryption_ready") -> try {
                val kp = api.post("/v1/keys/claim", JSONObject().put("user_id", conv.peer.id))
                val groupId = "mcxus:$conversationId:${randomHex()}".toByteArray()
                val welcome = withContext(Dispatchers.IO) {
                    mls.createDirect(groupId, Base64.decode(kp.getString("key_package"), Base64.NO_WRAP))
                }
                api.post(
                    "/v1/conversations/$conversationId/welcome",
                    JSONObject().put("device_id", deviceId).put("recipient_user_id", conv.peer.id).put("payload", b64(welcome)),
                )
                store.put("group:$conversationId", hex(groupId))
                refreshConversations()
                Readiness.Ready
            } catch (e: ApiError) {
                when (e.code) {
                    "already_initialised" -> Readiness.Waiting("${conv.peer.name}'s phone is setting up encryption…")
                    "no_key_packages" -> Readiness.Failed(e.message)
                    else -> throw e
                }
            }
            fresh.getBoolean("started_by_me") -> Readiness.Failed(
                "This chat was set up on your previous install and its keys are gone. Ask ${conv.peer.name} to start a new chat.",
            )
            else -> Readiness.Waiting("Receiving encryption keys from ${conv.peer.name}…")
        }
    }

    /** Encrypt and send. Returns false if the chat is not ready yet. */
    suspend fun send(conversationId: String, payload: String): Boolean {
        if (ensureReady(conversationId) != Readiness.Ready) return false
        lock.withLock {
            val gid = group(conversationId) ?: return false
            val ciphertext = withContext(Dispatchers.IO) { mls.encrypt(gid, payload.toByteArray(Charsets.UTF_8)) }
            val sent = api.post(
                "/v1/conversations/$conversationId/messages",
                JSONObject().put("device_id", deviceId).put("payload", b64(ciphertext)),
            )
            store.add(conversationId, sent.getLong("id"), true, payload, parseTime(sent.getString("created_at")), false)
        }
        publish()
        return true
    }

    fun conversation(id: String): Conversation? = _conversations.value.firstOrNull { it.id == id }

    fun messages(conversationId: String): List<LocalMessage> = store.messages(conversationId)

    fun markRead(conversationId: String) {
        store.markRead(conversationId)
        publish()
    }

    /** 60-digit number both people can compare to confirm nobody is in the middle. */
    fun safetyNumber(conversationId: String): String? = group(conversationId)?.let { runCatching { mls.safetyNumber(it) }.getOrNull() }

    companion object {
        private const val TAG = "McXusChat"
        private const val MIN_KEY_PACKAGES = 10
        private const val UPLOAD_KEY_PACKAGES = 20
        private val random = SecureRandom()

        /** Opens the encrypted state on a background thread (native code). */
        suspend fun create(context: Context, api: Api, userId: String): ChatEngine = withContext(Dispatchers.IO) {
            val state = File(context.filesDir, "mls-$userId.bin").path
            val mls = MlsClient.open(state, "user:$userId")
            ChatEngine(api, userId, ChatStore(context.applicationContext, userId), mls)
        }

        fun b64(bytes: ByteArray): String = Base64.encodeToString(bytes, Base64.NO_WRAP)
        fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it) }
        fun unhex(s: String): ByteArray = ByteArray(s.length / 2) { s.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
        private fun randomHex(): String = hex(ByteArray(8).also(random::nextBytes))

        fun parseTime(iso: String?): Long =
            if (iso.isNullOrEmpty() || iso == "null") 0L else OffsetDateTime.parse(iso).toInstant().toEpochMilli()
    }
}

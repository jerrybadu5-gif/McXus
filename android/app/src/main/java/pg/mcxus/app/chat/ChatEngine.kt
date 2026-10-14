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
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONArray
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
    val kind: String,
    val peer: Peer?,
    val title: String?,
    val memberCount: Int,
    val myRole: String,
    val listingId: String?,
    val encryptionReady: Boolean,
    val startedByMe: Boolean,
    val lastPreview: String,
    val lastAt: Long,
    val unread: Int,
) {
    val isGroup: Boolean get() = kind == "group"
    val name: String get() = if (isGroup) title ?: "Group" else peer?.name ?: "Chat"
    /** Stable key for avatar colours. */
    val avatarKey: String get() = peer?.id ?: id
}

data class Member(val id: String, val name: String, val role: String, val badge: String)

data class GroupInfo(val id: String, val title: String, val epoch: Long, val members: List<Member>)

/** A new message from someone else, for notifications. */
data class Incoming(val conversationId: String, val message: LocalMessage)

/** Result of getting a chat ready for encrypted messages. */
sealed class Readiness {
    data object Ready : Readiness()
    data class Waiting(val why: String) : Readiness()
    data class Failed(val why: String) : Readiness()
}

/**
 * End-to-end encrypted chat on this phone (ADR 0008, groups in ADR 0010).
 *
 * - Keys and group state live in an OpenMLS state file in app-private storage (filesDir/mls-<user>.bin).
 * - The server only relays ciphertext. A direct chat starts by claiming one of the other person's one-time
 *   KeyPackages and uploading a Welcome (first Welcome wins). A group is created on this phone; admins add and
 *   remove people with MLS Commits that the server accepts once per epoch.
 * - A long-poll loop (/v1/messages/sync?wait=25) delivers messages while the app runs; a push wakes it when
 *   closed ([syncOnce]). One shared cursor and one lock make sure each message is processed exactly once.
 * - Photos and voice notes are sealed with a per-file key ([Media]) that travels inside the encrypted message.
 * - Decrypted messages are kept only in [ChatStore].
 */
class ChatEngine private constructor(
    private val api: Api,
    val userId: String,
    private val store: ChatStore,
    private val mls: MlsClient,
    private val mediaDir: File,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val lock = Mutex()
    private var loop: Job? = null
    private var deviceId: String = ""
    private var cursor: Long = store.get("cursor")?.toLong() ?: 0L

    private val _version = MutableStateFlow(0L)
    /** Bumped whenever messages or chats change, so screens re-read the store. */
    val version: StateFlow<Long> = _version

    private val _conversations = MutableStateFlow<List<Conversation>>(emptyList())
    val conversations: StateFlow<List<Conversation>> = _conversations

    private val _online = MutableStateFlow(false)
    val online: StateFlow<Boolean> = _online

    private val _incoming = MutableSharedFlow<Incoming>(extraBufferCapacity = 64)
    val incoming: SharedFlow<Incoming> = _incoming

    private var serverConversations: List<JSONObject> = emptyList()
    private val groupCache = mutableMapOf<String, GroupInfo>()

    val device: String get() = deviceId

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
        ensureDevice()
        topUpKeyPackages()
        refreshConversations()
        _online.value = true
    }

    private suspend fun ensureDevice() {
        if (deviceId.isNotEmpty()) return
        deviceId = store.get("device_id") ?: api.post("/v1/devices", JSONObject().put("name", android.os.Build.MODEL ?: "Android"))
            .getString("device_id").also { store.put("device_id", it) }
    }

    /** Send this phone's Firebase token so the server can wake it (null = no pushes). */
    suspend fun registerPushToken(token: String?) {
        ensureDevice()
        api.post("/v1/devices/$deviceId/push-token", JSONObject().put("token", token ?: JSONObject.NULL))
    }

    /** Keep at least 10 unused KeyPackages on the server so people can add this phone while it is offline. */
    private suspend fun topUpKeyPackages() {
        val unclaimed = api.obj("/v1/keys/count?device_id=$deviceId").getInt("unclaimed")
        if (unclaimed >= MIN_KEY_PACKAGES) return
        val packages = withContext(Dispatchers.IO) { mls.keyPackages(UPLOAD_KEY_PACKAGES.toUInt()) }
        val body = JSONObject().put("device_id", deviceId).put("key_packages", JSONArray(packages.map { b64(it) }))
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
            val p = c.optJSONObject("peer")
            Conversation(
                id = id,
                kind = c.optString("kind", "direct"),
                peer = p?.let {
                    Peer(it.getString("id"), it.getString("name"), it.optString("badge"),
                        if (it.isNull("rating")) null else it.getString("rating"), it.optInt("reviews"))
                },
                title = if (c.isNull("title")) null else c.optString("title"),
                memberCount = c.optInt("member_count", 2),
                myRole = c.optString("my_role", "member"),
                listingId = if (c.isNull("listing_id")) null else c.getString("listing_id"),
                encryptionReady = c.getBoolean("encryption_ready"),
                startedByMe = c.getBoolean("started_by_me"),
                lastPreview = s?.let { Payload.preview(it.first) }
                    ?: if (c.optString("kind") == "group") "Group created" else "Tap to start an encrypted chat",
                lastAt = s?.second ?: parseTime(c.optString("created_at")),
                unread = s?.third ?: 0,
            )
        }.sortedByDescending { it.lastAt }
        _version.value++
    }

    private suspend fun syncForever() {
        while (true) {
            val batch = api.list("/v1/messages/sync?after=$cursor&limit=200&wait=25")
            _online.value = true
            if (batch.length() > 0) process(batch)
        }
    }

    /** One quick sync without waiting (used when a push arrives while the app is closed). */
    suspend fun syncOnce() {
        ensureDevice()
        val batch = api.list("/v1/messages/sync?after=$cursor&limit=200&wait=0")
        if (batch.length() > 0) process(batch)
    }

    private suspend fun process(batch: JSONArray) {
        val effects = lock.withLock { processLocked(batch) }
        if (effects.unknownChat) refreshConversations() else publish()
        if (effects.gotWelcome) runCatching { topUpKeyPackages() }
        for ((conv, users) in effects.leftGroups) {
            // Someone left: if I am an admin, take them out of the encryption too (first admin wins).
            if (conversation(conv)?.myRole == "admin") runCatching { removeMembers(conv, users) }
        }
    }

    private class Effects {
        var unknownChat = false
        var gotWelcome = false
        val leftGroups = mutableListOf<Pair<String, List<String>>>()
    }

    /** Must hold [lock]. Skips anything at or below the cursor, so no message is ever processed twice. */
    private fun processLocked(batch: JSONArray): Effects {
        val effects = Effects()
        for (i in 0 until batch.length()) {
            val m = batch.getJSONObject(i)
            val id = m.getLong("id")
            if (id <= cursor) continue
            val conv = m.getString("conversation_id")
            if (serverConversations.none { it.getString("id") == conv }) effects.unknownChat = true
            when (m.getString("kind")) {
                "welcome" -> effects.gotWelcome = true
                "event" -> {
                    val e = JSONObject(String(Base64.decode(m.getString("payload"), Base64.NO_WRAP)))
                    groupCache.remove(conv)
                    if (e.optString("type") == "left") {
                        val users = e.optJSONArray("users")?.let { a -> (0 until a.length()).map { a.getString(it) } }.orEmpty()
                        effects.leftGroups += conv to users
                    }
                    if (e.optString("type") in listOf("added", "removed")) effects.unknownChat = true
                }
            }
            handle(m, conv)
            cursor = id
            store.put("cursor", cursor.toString())
        }
        return effects
    }

    private fun handle(m: JSONObject, conv: String) {
        val payload = Base64.decode(m.getString("payload"), Base64.NO_WRAP)
        val at = parseTime(m.getString("created_at"))
        val sender = m.getString("sender_user_id")
        when (m.getString("kind")) {
            "welcome" -> if (group(conv) == null) {
                try {
                    store.put("group:$conv", hex(mls.join(payload)))
                } catch (e: Exception) {
                    Log.w(TAG, "join failed", e)
                    store.add(conv, null, false, Payload.system("Could not open this encrypted chat on this phone."), at, false)
                }
            }
            "event" -> {
                val e = JSONObject(String(payload)).put("t", "event")
                store.add(conv, m.getLong("id"), sender == userId, e.toString(), at, false, sender)
            }
            "commit" -> {
                if (m.getString("sender_device_id") == deviceId) return // my own change: applied when accepted
                val gid = group(conv) ?: return // made before this phone joined
                try {
                    if (mls.decrypt(gid, payload).kind == "removed") {
                        store.put("removed:$conv", "1")
                        store.add(conv, null, false, Payload.system("You were removed from this group."), at, false)
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "commit failed", e)
                }
            }
            else -> {
                if (m.getString("sender_device_id") == deviceId) return // my own message: stored when sent
                val gid = group(conv)
                if (gid == null) {
                    store.add(conv, m.getLong("id"), false, Payload.system("A message could not be decrypted (no keys)."), at, false)
                    return
                }
                try {
                    val d = mls.decrypt(gid, payload)
                    val text = d.plaintext ?: return
                    val body = if (d.sender == "user:$sender") {
                        String(text, Charsets.UTF_8)
                    } else {
                        Payload.system("Warning: a message failed the sender check and was hidden.")
                    }
                    val mine = sender == userId
                    store.add(conv, m.getLong("id"), mine, body, at, !mine, sender)
                    if (!mine) store.message(m.getLong("id"))?.let { _incoming.tryEmit(Incoming(conv, it)) }
                } catch (e: Exception) {
                    Log.w(TAG, "decrypt failed", e)
                    store.add(conv, m.getLong("id"), false, Payload.system("A message could not be decrypted."), at, false, sender)
                }
            }
        }
    }

    private fun group(conv: String): ByteArray? = store.get("group:$conv")?.let(::unhex)

    fun isRemoved(conv: String): Boolean = store.get("removed:$conv") == "1"

    // ---------- direct chats ----------

    /** Open (or find) the one-to-one chat with [peerId]; optionally linked to a listing. */
    suspend fun open(peerId: String, listingId: String? = null): String {
        val body = JSONObject().put("peer_user_id", peerId)
        if (listingId != null) body.put("listing_id", listingId)
        val conv = api.post("/v1/conversations", body)
        refreshConversations()
        return conv.getString("id")
    }

    /** Make sure this phone can encrypt for [conversationId]; sets a direct chat up the first time. */
    suspend fun ensureReady(conversationId: String): Readiness = lock.withLock {
        val conv = conversation(conversationId) ?: return@withLock Readiness.Failed("Chat not found")
        if (conv.isGroup) {
            return@withLock when {
                isRemoved(conversationId) -> Readiness.Failed("You are no longer in this group.")
                group(conversationId) != null -> Readiness.Ready
                else -> Readiness.Waiting("Receiving the group's encryption keys…")
            }
        }
        if (group(conversationId) != null) return@withLock Readiness.Ready
        val peer = conv.peer ?: return@withLock Readiness.Failed("Chat not found")
        val fresh = api.post("/v1/conversations", JSONObject().put("peer_user_id", peer.id))
        when {
            !fresh.getBoolean("encryption_ready") -> try {
                val kp = api.post("/v1/keys/claim", JSONObject().put("user_id", peer.id))
                val groupId = newGroupId(conversationId)
                val welcome = mls.createDirect(groupId, Base64.decode(kp.getString("key_package"), Base64.NO_WRAP))
                api.post(
                    "/v1/conversations/$conversationId/welcome",
                    JSONObject().put("device_id", deviceId).put("recipient_user_id", peer.id).put("payload", b64(welcome)),
                )
                store.put("group:$conversationId", hex(groupId))
                Readiness.Ready
            } catch (e: ApiError) {
                when (e.code) {
                    "already_initialised" -> Readiness.Waiting("${peer.name}'s phone is setting up encryption…")
                    "no_key_packages", "too_many_claims" -> Readiness.Failed(e.message)
                    else -> throw e
                }
            }
            fresh.getBoolean("started_by_me") -> Readiness.Failed(
                "This chat was set up on your previous install and its keys are gone. Ask ${peer.name} to start a new chat.",
            )
            else -> Readiness.Waiting("Receiving encryption keys from ${peer.name}…")
        }
    }.also { if (it == Readiness.Ready) runCatching { refreshConversations() } }

    // ---------- groups ----------

    data class AddResult(val added: List<String>, val withoutApp: List<String>)

    /** Create a group (I am admin) and add [memberIds]. Returns the conversation id. */
    suspend fun createGroup(title: String, memberIds: List<String>): Pair<String, AddResult> {
        ensureDevice()
        val conv = api.post("/v1/groups", JSONObject().put("title", title)).getString("id")
        lock.withLock {
            val gid = newGroupId(conv)
            mls.createGroup(gid)
            store.put("group:$conv", hex(gid))
        }
        val result = if (memberIds.isEmpty()) AddResult(emptyList(), emptyList()) else addMembers(conv, memberIds)
        refreshConversations()
        return conv to result
    }

    /**
     * Admin adds people: claim one KeyPackage each, make one MLS Commit + Welcome, and send them. If someone
     * else changed the group first (409 stale_epoch), apply their change and try once more.
     */
    suspend fun addMembers(conv: String, userIds: List<String>): AddResult {
        val result = lock.withLock {
            val gid = group(conv) ?: throw IllegalStateException("This phone has no keys for the group")
            val ok = mutableListOf<String>()
            val missing = mutableListOf<String>()
            val packages = mutableListOf<ByteArray>()
            for (id in userIds.distinct()) {
                try {
                    val kp = api.post("/v1/keys/claim", JSONObject().put("user_id", id).put("group_id", conv))
                    packages += Base64.decode(kp.getString("key_package"), Base64.NO_WRAP)
                    ok += id
                } catch (e: ApiError) {
                    if (e.code in listOf("no_key_packages", "too_many_claims")) missing += id
                    else if (e.code != "already_member") throw e
                }
            }
            if (ok.isNotEmpty()) {
                commitWithRetry(conv, gid) {
                    val change = mls.addMembers(gid, packages)
                    api.post(
                        "/v1/groups/$conv/members",
                        JSONObject().put("device_id", deviceId).put("user_ids", JSONArray(ok)).put("epoch", change.epoch.toLong())
                            .put("commit", b64(change.commit)).put("welcome", b64(change.welcome!!)),
                    )
                }
            }
            AddResult(ok, missing)
        }
        groupCache.remove(conv)
        refreshConversations()
        return result
    }

    /** Admin removes people (also used to finish someone's "leave" in the encryption). */
    suspend fun removeMembers(conv: String, userIds: List<String>) {
        lock.withLock {
            val gid = group(conv) ?: return@withLock
            val identities = userIds.map { "user:$it" }
            val inGroup = mls.members(gid).filter { it in identities }
            if (inGroup.isEmpty()) {
                // Already out of the encryption; only the server list needs updating (no commit needed).
                return@withLock
            }
            commitWithRetry(conv, gid) {
                val change = mls.removeMembers(gid, inGroup)
                api.post(
                    "/v1/groups/$conv/members/remove",
                    JSONObject().put("device_id", deviceId).put("user_ids", JSONArray(userIds)).put("epoch", change.epoch.toLong())
                        .put("commit", b64(change.commit)),
                )
            }
        }
        groupCache.remove(conv)
        refreshConversations()
    }

    /** Must hold [lock]. Runs [attempt] (create change + send). On a refused epoch, catches up and retries. */
    private suspend fun commitWithRetry(conv: String, gid: ByteArray, attempt: suspend () -> Unit) {
        repeat(3) { n ->
            try {
                attempt()
                mls.confirmChange(gid)
                return
            } catch (e: ApiError) {
                mls.discardChange(gid)
                if (e.code != "stale_epoch" || n == 2) throw e
                // Apply the change that beat ours, then make ours again on the new epoch.
                val batch = api.list("/v1/messages/sync?after=$cursor&limit=200&wait=0")
                processLocked(batch)
            } catch (e: Exception) {
                runCatching { mls.discardChange(gid) }
                throw e
            }
        }
    }

    suspend fun leaveGroup(conv: String) {
        api.post("/v1/groups/$conv/leave")
        store.put("removed:$conv", "1")
        groupCache.remove(conv)
        refreshConversations()
    }

    suspend fun setRole(conv: String, userId: String, role: String) {
        api.post("/v1/groups/$conv/role", JSONObject().put("user_id", userId).put("role", role))
        groupCache.remove(conv)
        refreshConversations()
    }

    suspend fun rename(conv: String, title: String) {
        api.put("/v1/groups/$conv", JSONObject().put("title", title))
        groupCache.remove(conv)
        refreshConversations()
    }

    /** Members and roles (cached until the group changes). */
    suspend fun groupInfo(conv: String, refresh: Boolean = false): GroupInfo {
        if (!refresh) groupCache[conv]?.let { return it }
        val g = api.obj("/v1/groups/$conv")
        val members = g.getJSONArray("members").let { a ->
            (0 until a.length()).map { a.getJSONObject(it) }.map { m ->
                val u = m.getJSONObject("user")
                Member(u.getString("id"), u.getString("name"), m.getString("role"), u.optString("badge"))
            }
        }
        return GroupInfo(g.getString("id"), g.optString("title"), g.getLong("epoch"), members).also { groupCache[conv] = it }
    }

    // ---------- sending ----------

    /** Encrypt and send. Returns false if the chat is not ready yet. */
    suspend fun send(conversationId: String, payload: String): Boolean {
        if (ensureReady(conversationId) != Readiness.Ready) return false
        lock.withLock {
            val gid = group(conversationId) ?: return false
            val ciphertext = mls.encrypt(gid, payload.toByteArray(Charsets.UTF_8))
            val sent = api.post(
                "/v1/conversations/$conversationId/messages",
                JSONObject().put("device_id", deviceId).put("payload", b64(ciphertext)),
            )
            store.add(conversationId, sent.getLong("id"), true, payload, parseTime(sent.getString("created_at")), false, userId)
        }
        publish()
        return true
    }

    /** Photo: [jpeg] is already shrunk; [thumb] is a tiny preview shown while the photo downloads. */
    suspend fun sendImage(conv: String, jpeg: ByteArray, w: Int, h: Int, thumb: ByteArray, caption: String): Boolean {
        if (ensureReady(conv) != Readiness.Ready) return false
        val sealed = Media.seal(jpeg)
        val blob = api.postBytes("/v1/conversations/$conv/blobs", sealed.ciphertext).getString("id")
        cache(blob).writeBytes(jpeg) // the sender never downloads its own photo
        return send(conv, Payload.image(blob, b64(sealed.key), sealed.sha256, w, h, b64(thumb), caption))
    }

    suspend fun sendVoice(conv: String, audio: ByteArray, durationMs: Long): Boolean {
        if (ensureReady(conv) != Readiness.Ready) return false
        val sealed = Media.seal(audio)
        val blob = api.postBytes("/v1/conversations/$conv/blobs", sealed.ciphertext).getString("id")
        cache(blob).writeBytes(audio)
        return send(conv, Payload.voice(blob, b64(sealed.key), sealed.sha256, durationMs))
    }

    /** The decrypted file for an image/voice message: from this phone's cache, or downloaded and opened. */
    suspend fun mediaFile(p: JSONObject): File = withContext(Dispatchers.IO) {
        val blob = p.getString("blob")
        val file = cache(blob)
        if (!file.exists()) {
            val sealed = api.getBytes("/v1/blobs/$blob")
            val plain = Media.open(sealed, Base64.decode(p.getString("key"), Base64.NO_WRAP), p.getString("sha"))
            val tmp = File(file.path + ".tmp")
            tmp.writeBytes(plain)
            tmp.renameTo(file)
        }
        file
    }

    private fun cache(blob: String): File = File(mediaDir, blob.filter { it.isLetterOrDigit() || it == '-' })

    fun conversation(id: String): Conversation? = _conversations.value.firstOrNull { it.id == id }

    fun messages(conversationId: String): List<LocalMessage> = store.messages(conversationId)

    fun markRead(conversationId: String) {
        store.markRead(conversationId)
        publish()
    }

    /** 60-digit number members can compare to confirm nobody is in the middle. */
    fun safetyNumber(conversationId: String): String? = group(conversationId)?.let { runCatching { mls.safetyNumber(it) }.getOrNull() }

    private fun newGroupId(conv: String) = "mcxus:$conv:${randomHex()}".toByteArray()

    companion object {
        private const val TAG = "McXusChat"
        private const val MIN_KEY_PACKAGES = 10
        private const val UPLOAD_KEY_PACKAGES = 20
        private val random = SecureRandom()

        /** Opens the encrypted state on a background thread (native code). */
        suspend fun create(context: Context, api: Api, userId: String): ChatEngine = withContext(Dispatchers.IO) {
            val state = File(context.filesDir, "mls-$userId.bin").path
            val mls = MlsClient.open(state, "user:$userId")
            val media = File(context.filesDir, "chat-media-$userId").apply { mkdirs() }
            ChatEngine(api, userId, ChatStore(context.applicationContext, userId), mls, media)
        }

        fun b64(bytes: ByteArray): String = Base64.encodeToString(bytes, Base64.NO_WRAP)
        fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it) }
        fun unhex(s: String): ByteArray = ByteArray(s.length / 2) { s.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
        private fun randomHex(): String = hex(ByteArray(8).also(random::nextBytes))

        fun parseTime(iso: String?): Long =
            if (iso.isNullOrEmpty() || iso == "null") 0L else OffsetDateTime.parse(iso).toInstant().toEpochMilli()
    }
}

package pg.mcxus.app

import android.content.Context
import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.withLock
import pg.mcxus.app.chat.ChatEngine
import pg.mcxus.app.net.Api
import pg.mcxus.app.net.ApiError
import pg.mcxus.app.net.Session
import uniffi.mcxus_crypto.CryptoException
import java.io.IOException

/** Everything the screens share: who is signed in, the API client, the chat engine and the message bar. */
class App(context: Context, val scope: CoroutineScope) {
    private val appContext = context.applicationContext
    val session = Session(appContext)
    val api = Api(session)
    val snackbar = SnackbarHostState()

    var signedIn by mutableStateOf(session.signedIn)
        private set
    var chat by mutableStateOf<ChatEngine?>(null)
        private set
    var displayName by mutableStateOf("")

    /** The account is frozen: only the frozen screen (reason, appeal) is shown. */
    var frozen by mutableStateOf(false)
        private set

    /** Disputes waiting for my answer (badge on Me and Me › Disputes). */
    var disputeAttention by mutableStateOf(0)
        private set

    /** A card to send with the next message in a chat (e.g. the listing from Discover › Message). */
    val pendingCard = androidx.compose.runtime.mutableStateMapOf<String, String>()

    /** Short message shown just above the keyboard (or the tab bar). Errors are shown in red. */
    fun say(message: String, error: Boolean = false) {
        scope.launch {
            snackbar.currentSnackbarData?.dismiss()
            snackbar.showSnackbar(message, actionLabel = if (error) ERROR else null, duration = androidx.compose.material3.SnackbarDuration.Long)
        }
    }

    /** Server feature level (from /health). The app needs [MIN_SERVER_LEVEL]; older servers answer "Not Found". */
    var serverLevel by mutableStateOf<Int?>(null)
        private set
    val serverOutdated: Boolean get() = serverLevel?.let { it < MIN_SERVER_LEVEL } == true

    fun checkServer() {
        scope.launch {
            serverLevel = runCatching { api.obj("/health").optInt("api_level", 1) }.getOrNull()
        }
    }

    /** Run [block] and turn failures into a readable message instead of a crash. */
    fun launch(onDone: (() -> Unit)? = null, onError: ((String) -> Unit)? = null, block: suspend () -> Unit): Job = scope.launch {
        try {
            block()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            if (e is ApiError && e.code == "account_frozen") {
                markFrozen()
                return@launch
            }
            val text = explain(e)
            onError?.invoke(text)
            say(text, error = true)
            if (e is ApiError && e.status == 401) signOut()
        } finally {
            onDone?.invoke()
        }
    }

    fun explain(e: Throwable): String = when (e) {
        // FastAPI's own 404 (no such address) means the server is older than this app.
        is ApiError -> if (e.status == 404 && e.message == "Not Found") OUTDATED.also { checkServer() } else e.message
        is IOException -> "Can't reach the McXus server. Check Wi-Fi and the server address in Me › Server."
        is CryptoException.Failed -> "Encryption error: ${e.reason}"
        else -> e.message ?: "Something went wrong"
    }

    fun onSignedIn(token: String, userId: String) {
        session.token = token
        session.userId = userId
        signedIn = true
        startChat()
        usedNow() // signing in on this device means it is the one in use
    }

    /** Which chat is on screen (no notification for it) and whether McXus is in front. */
    var openChat: String? = null
    var inForeground = false

    private val chatMutex = kotlinx.coroutines.sync.Mutex()

    fun startChat() {
        if (session.userId == null || chat != null) return
        launch { ensureChat() }
    }

    /** The running chat engine, starting it if needed (also used when a push wakes a closed app). */
    suspend fun ensureChat(): ChatEngine? = chatMutex.withLock {
        chat?.let { return@withLock it }
        if (frozen) return@withLock null
        val user = session.userId ?: return@withLock null
        checkServer()
        val engine = ChatEngine.create(appContext, api, user)
        chat = engine
        engine.start()
        scope.launch { engine.incoming.collect { Notifier.show(appContext, this@App, engine, it) } }
        watchDisputes()
        Push.register(appContext) { token -> scope.launch { runCatching { engine.registerPushToken(token) } } }
        engine
    }

    /** Check whether the account is frozen (GET /v1/me works for frozen accounts too). */
    suspend fun refreshStatus() {
        val me = runCatching { api.obj("/v1/me") }.getOrNull() ?: return
        if (me.optString("status") == "frozen") markFrozen() else if (frozen) {
            frozen = false // unfrozen by staff: start chat again
            startChat()
        }
    }

    private fun markFrozen() {
        if (frozen) return
        frozen = true
        chat?.stop()
        chat = null
    }

    /**
     * Ask the server which disputes need my answer; update the badge and notify once per new update
     * (a new dispute, an offer, a decision). Called every 30 s while McXus is open and when a push arrives.
     */
    suspend fun checkDisputes() {
        if (!signedIn || frozen) return
        val att = runCatching { api.obj("/v1/disputes/attention") }.getOrNull() ?: return
        disputeAttention = att.optInt("count")
        val items = att.optJSONArray("items") ?: return
        val seen = session.notifiedDisputes
        val fresh = (0 until items.length()).map { items.getJSONObject(it) }
            .filter { "${it.optString("order_id")}:${it.optLong("last_event")}" !in seen }
        fresh.forEach { Notifier.showDispute(appContext, this, it.optString("order_id"), it.optString("title"), it.optString("attention")) }
        if (fresh.isNotEmpty()) session.notifiedDisputes = seen + fresh.map { "${it.optString("order_id")}:${it.optLong("last_event")}" }
    }

    private var watching: Job? = null

    private fun watchDisputes() {
        if (watching?.isActive == true) return
        watching = scope.launch {
            while (true) {
                if (inForeground) checkDisputes()
                kotlinx.coroutines.delay(30_000)
            }
        }
    }

    /**
     * Put dispute news into the buyer–seller chat (end-to-end encrypted, like any message), so the other person
     * gets the usual chat notification and can tap through to the dispute. Best effort: never blocks the action.
     */
    fun tellInChat(peerId: String, orderId: String, title: String, body: String) {
        scope.launch {
            runCatching {
                val engine = ensureChat() ?: return@runCatching
                val conv = engine.open(peerId)
                if (engine.ensureReady(conv) == pg.mcxus.app.chat.Readiness.Ready) {
                    engine.send(conv, pg.mcxus.app.chat.Payload.dispute(orderId, title, body))
                }
            }
        }
    }

    private var activatedAt = 0L

    /** The person is using this device (app opened or touched); at most once a minute. See [ChatEngine.activate]. */
    fun usedNow() {
        val now = System.currentTimeMillis()
        if (!signedIn || now - activatedAt < 60_000) return
        activatedAt = now
        launch {
            refreshStatus()
            if (!frozen) ensureChat()?.activate()
            checkDisputes()
        }
    }

    fun signOut() {
        activatedAt = 0L
        frozen = false
        disputeAttention = 0
        watching?.cancel()
        chat?.let { engine -> scope.launch { runCatching { engine.registerPushToken(null) } } }
        chat?.stop()
        chat = null
        session.signOut()
        signedIn = false
    }
}

const val MIN_SERVER_LEVEL = 7
const val ERROR = "error"
const val OUTDATED = "The McXus server is older than this app. On the laptop run the task \"McXus: start backend\" (it rebuilds the server), then try again."

val LocalApp = staticCompositionLocalOf<App> { error("App not provided") }

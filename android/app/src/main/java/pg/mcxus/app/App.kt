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

    fun say(message: String) {
        scope.launch { snackbar.currentSnackbarData?.dismiss(); snackbar.showSnackbar(message) }
    }

    /** Run [block] and turn failures into a readable message instead of a crash. */
    fun launch(onDone: (() -> Unit)? = null, block: suspend () -> Unit): Job = scope.launch {
        try {
            block()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            say(explain(e))
            if (e is ApiError && e.status == 401) signOut()
        } finally {
            onDone?.invoke()
        }
    }

    fun explain(e: Throwable): String = when (e) {
        is ApiError -> e.message
        is IOException -> "Can't reach the McXus server. Check Wi-Fi and the server address in Me › Server."
        is CryptoException.Failed -> "Encryption error: ${e.reason}"
        else -> e.message ?: "Something went wrong"
    }

    fun onSignedIn(token: String, userId: String) {
        session.token = token
        session.userId = userId
        signedIn = true
        startChat()
    }

    fun startChat() {
        val user = session.userId ?: return
        if (chat != null) return
        launch {
            chat = ChatEngine.create(appContext, api, user).also { it.start() }
        }
    }

    fun signOut() {
        chat?.stop()
        chat = null
        session.signOut()
        signedIn = false
    }
}

val LocalApp = staticCompositionLocalOf<App> { error("App not provided") }

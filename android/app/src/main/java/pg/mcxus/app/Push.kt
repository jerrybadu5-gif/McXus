package pg.mcxus.app

import android.content.Context
import android.util.Log
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Firebase push, only when the build includes google-services.json (see docs/FIREBASE-PUSH.md). Without it
 * McXus still works; messages arrive while the app is open.
 */
object Push {
    fun available(context: Context): Boolean = FirebaseApp.getApps(context).isNotEmpty()

    fun register(context: Context, onToken: (String) -> Unit) {
        if (!available(context)) return
        FirebaseMessaging.getInstance().token
            .addOnSuccessListener { onToken(it) }
            .addOnFailureListener { Log.w("McXusPush", "No push token: ${it.message}") }
    }
}

/** A push carries only {"t":"sync"}: fetch and decrypt new messages, then notify from the phone itself. */
class McXusMessagingService : FirebaseMessagingService() {
    private val app: App get() = (application as McXusApp).app

    override fun onNewToken(token: String) {
        app.chat?.let { engine -> app.scope.launch { runCatching { engine.registerPushToken(token) } } }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        if (!app.signedIn) return
        // Runs on a background thread; Android gives us a few seconds.
        runBlocking {
            withTimeoutOrNull(8_000) {
                val engine = app.ensureChat() ?: return@withTimeoutOrNull
                runCatching { engine.syncOnce() }
                app.checkDisputes() // a push may also mean a dispute update
                delay(300) // let the notification collector run
            }
        }
    }
}

package pg.mcxus.app

import android.app.Application
import kotlinx.coroutines.MainScope

/** Holds the one [App] for the whole process, so a push can start the chat engine with no screen open. */
class McXusApp : Application() {
    lateinit var app: App
        private set

    override fun onCreate() {
        super.onCreate()
        app = App(this, MainScope())
        Notifier.createChannel(this)
        if (app.signedIn) app.startChat()
    }
}

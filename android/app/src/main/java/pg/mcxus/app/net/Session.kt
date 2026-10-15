package pg.mcxus.app.net

import android.content.Context

/**
 * Who is signed in and which server to talk to. Stored in this app's private storage (other apps cannot
 * read it; backups are switched off in the manifest). Handover PINs are kept in memory only.
 */
class Session(context: Context, name: String = "mcxus") {
    private val prefs = context.getSharedPreferences(name, Context.MODE_PRIVATE)

    var server: String
        get() = prefs.getString("server", "") ?: ""
        set(value) = prefs.edit().putString("server", value.trim()).apply()

    var token: String?
        get() = prefs.getString("token", null)
        set(value) = prefs.edit().putString("token", value).apply()

    var userId: String?
        get() = prefs.getString("user_id", null)
        set(value) = prefs.edit().putString("user_id", value).apply()

    var phone: String
        get() = prefs.getString("phone", "") ?: ""
        set(value) = prefs.edit().putString("phone", value).apply()

    /** Show who wrote and the text in notifications. Off by default (privacy first): "McXus · New message" only. */
    var showPreviews: Boolean
        get() = prefs.getBoolean("show_previews_v2", false)
        set(value) = prefs.edit().putBoolean("show_previews_v2", value).apply()

    /** Dispute updates already notified ("orderId:eventId"), so each one is announced once. */
    var notifiedDisputes: Set<String>
        get() = prefs.getStringSet("notified_disputes", emptySet()) ?: emptySet()
        set(value) = prefs.edit().putStringSet("notified_disputes", value.toList().takeLast(200).toSet()).apply()

    var role: String = "user"
    var tier: Int = 0

    /** order id -> PIN, for this app run only. */
    val pins = mutableMapOf<String, String>()

    val signedIn: Boolean get() = !token.isNullOrEmpty()

    fun signOut() {
        prefs.edit().remove("token").remove("user_id").apply()
        pins.clear()
    }
}

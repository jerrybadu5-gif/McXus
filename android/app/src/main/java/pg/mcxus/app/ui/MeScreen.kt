package pg.mcxus.app.ui

import android.text.InputType
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import org.json.JSONObject
import pg.mcxus.app.BuildConfig
import pg.mcxus.app.MainActivity
import pg.mcxus.app.util.Format

/** Profile and store name, my listings, server address, sign out. */
class MeScreen(main: MainActivity) : Screen(main) {
    override val title = "Me"

    private lateinit var name: EditText
    private lateinit var store: EditText
    private lateinit var bio: EditText
    private lateinit var info: LinearLayout
    private lateinit var listings: LinearLayout

    override fun build(): View {
        val ctx = main
        name = Ui.input(ctx, "Your name")
        store = Ui.input(ctx, "Store name (optional)")
        bio = Ui.input(ctx, "About you or your store",
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE)
        info = Ui.column(ctx, 0)
        listings = Ui.column(ctx, 0)
        val server = Ui.input(ctx, "Server", InputType.TYPE_TEXT_VARIATION_URI, session.server)
        return Ui.scroll(ctx, Ui.column(ctx, 16,
            info,
            Ui.label(ctx, "Profile"), name, store, bio,
            Ui.button(ctx, "Save profile") { save() },
            Ui.label(ctx, "My listings"), listings,
            Ui.label(ctx, "Server"), server,
            Ui.button(ctx, "Save server", primary = false) {
                session.server = server.text.toString()
                main.toast("Server saved")
            },
            Ui.button(ctx, "Sign out", primary = false) {
                session.signOut()
                main.show(SignInScreen(main), root = true)
            },
            Ui.muted(ctx, "McXus ${BuildConfig.VERSION_NAME} · sandbox preview"),
        ))
    }

    override fun load() {
        launch {
            val me = api.obj("/v1/me")
            info.addView(Ui.text(main, me.str("phone"), 17f, bold = true))
            info.addView(Ui.muted(main, "Verification level ${me.optInt("kyc_tier")} · role ${me.str("role")}"))
            name.setText(me.str("display_name"))
            val seller = api.obj("/v1/sellers/${me.str("id")}")
            store.setText(if (seller.optBoolean("is_store")) seller.str("name") else "")
            bio.setText(seller.str("bio"))
            info.addView(Ui.chip(main, Format.badge(seller.str("badge"))))
            val mine = api.list("/v1/me/listings").objects()
            if (mine.isEmpty()) listings.addView(Ui.muted(main, "You have no listings. Use the Sell tab."))
            mine.forEach { l ->
                listings.addView(Ui.card(main,
                    Ui.text(main, l.str("title"), bold = true),
                    Ui.muted(main, "${Format.kina(l.str("price"))} · ${l.optInt("quantity_available")} left · " +
                        l.str("status").replace('_', ' ')),
                ) { main.show(ListingScreen(main, l.str("id"))) })
            }
        }
    }

    private fun save() {
        val body = JSONObject()
            .put("display_name", name.text.toString().trim())
            .put("store_name", store.text.toString().trim().ifEmpty { null } ?: JSONObject.NULL)
            .put("bio", bio.text.toString().trim())
        launch {
            api.put("/v1/me/profile", body)
            main.toast("Profile saved")
        }
    }
}

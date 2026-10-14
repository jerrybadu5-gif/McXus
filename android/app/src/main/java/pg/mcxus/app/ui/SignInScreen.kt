package pg.mcxus.app.ui

import android.text.InputType
import android.view.View
import android.widget.EditText
import android.widget.TextView
import org.json.JSONObject
import pg.mcxus.app.MainActivity

class SignInScreen(main: MainActivity) : Screen(main) {
    override val title = "Sign in to McXus"
    override val showTabs = false

    private lateinit var server: EditText
    private lateinit var phone: EditText
    private lateinit var code: EditText
    private lateinit var hint: TextView

    override fun build(): View {
        val ctx = main
        server = Ui.input(ctx, "Server, e.g. http://192.168.1.20:8000", InputType.TYPE_TEXT_VARIATION_URI,
            session.server)
        phone = Ui.input(ctx, "Mobile number, e.g. 70000001", InputType.TYPE_CLASS_PHONE, session.phone)
        code = Ui.numberInput(ctx, "6-digit code")
        hint = Ui.muted(ctx, "")
        return Ui.scroll(ctx, Ui.column(ctx, 20,
            Ui.title(ctx, "Welcome"),
            Ui.muted(ctx, "SANDBOX — test Stars only, no real money."),
            Ui.label(ctx, "Server (shown by start-dev.ps1 -Lan on the laptop)"), server,
            Ui.label(ctx, "Mobile number"), phone,
            Ui.button(ctx, "Send code") { sendCode() },
            hint,
            Ui.label(ctx, "Code"), code,
            Ui.button(ctx, "Sign in") { verify() },
            Ui.muted(ctx, "Demo accounts: buyer 70000001, seller 70000002, second buyer 70000008."),
        ))
    }

    private fun sendCode() {
        session.server = server.text.toString()
        session.phone = phone.text.toString()
        launch {
            val r = api.post("/v1/auth/otp/request", JSONObject().put("phone", phone.text.toString()))
            val dev = r.str("dev_code")
            if (dev.isNotEmpty()) {
                code.setText(dev)
                hint.text = "Sandbox: no SMS is sent yet, so the code is filled in for you."
            } else {
                hint.text = "Code sent by SMS."
            }
        }
    }

    private fun verify() {
        session.server = server.text.toString()
        launch {
            val r = api.post("/v1/auth/otp/verify",
                JSONObject().put("phone", phone.text.toString()).put("code", code.text.toString()))
            session.token = r.getString("access_token")
            session.userId = r.getString("user_id")
            val me = api.obj("/v1/me")
            session.role = me.str("role")
            session.tier = me.optInt("kyc_tier")
            main.toast("Signed in")
            main.openTab(MarketScreen(main))
        }
    }
}

package pg.mcxus.app.ui

import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONObject
import pg.mcxus.app.MainActivity
import pg.mcxus.app.util.Format

/** Stars balance, limits, sandbox top-up and statement. Screenshots blocked. */
class WalletScreen(main: MainActivity) : Screen(main) {
    override val title = "Wallet"
    override val secure = true

    private lateinit var balance: TextView
    private lateinit var details: LinearLayout
    private lateinit var amount: EditText
    private lateinit var statement: LinearLayout

    override fun build(): View {
        val ctx = main
        balance = Ui.text(ctx, "…", 30f, bold = true, color = Ui.GREEN)
        details = Ui.column(ctx, 0)
        amount = Ui.numberInput(ctx, "Amount, e.g. 200", decimal = true)
        statement = Ui.column(ctx, 0)
        return Ui.scroll(ctx, Ui.column(ctx, 16,
            Ui.muted(ctx, "Your Stars (1 Star = K1)"), balance, details,
            Ui.label(ctx, "Add test Stars (sandbox only)"), amount,
            Ui.button(ctx, "Top up") { topUp() },
            Ui.label(ctx, "Statement"), statement,
        ))
    }

    override fun load() {
        launch {
            val w = api.obj("/v1/wallet")
            balance.text = Format.kina(w.str("balance"))
            details.removeAllViews()
            details.addView(Ui.muted(main, "Verification: level ${w.optInt("kyc_tier")} (${w.str("kyc_tier_name")})"))
            if (w.str("max_balance").isNotEmpty()) {
                details.addView(Ui.muted(main, "Limits: balance up to ${Format.kina(w.str("max_balance"))}, " +
                    "deposits ${Format.kina(w.str("monthly_in_used"))} of ${Format.kina(w.str("monthly_in_limit"))} this month"))
            }
            if (w.str("penalties_owed") != "0.00") {
                details.addView(Ui.text(main, "Penalties owed: ${Format.kina(w.str("penalties_owed"))} (taken from your next sale)",
                    color = Ui.RED))
            }
            statement.removeAllViews()
            val lines = api.list("/v1/wallet/statement?limit=50").objects()
            if (lines.isEmpty()) statement.addView(Ui.muted(main, "No transactions yet."))
            lines.forEach { line ->
                val amt = line.str("amount")
                statement.addView(Ui.card(main,
                    Ui.row(main,
                        Ui.weight(Ui.text(main, line.str("description"))),
                        Ui.text(main, (if (amt.startsWith("-")) "" else "+") + Format.kina(amt), bold = true,
                            color = if (amt.startsWith("-")) Ui.RED else Ui.GREEN),
                    ),
                    Ui.muted(main, Format.dateTime(line.str("at"))),
                ))
            }
        }
    }

    private fun topUp() {
        val value = Format.amount(amount.text.toString())
        if (value == null) {
            main.alert("Enter an amount like 200 or 200.50")
            return
        }
        launch {
            api.post("/v1/wallet/sandbox-topup", JSONObject().put("amount", value), idempotent = true)
            amount.setText("")
            main.toast("Added ${Format.kina(value)} test Stars")
            load()
        }
    }
}

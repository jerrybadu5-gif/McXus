package pg.mcxus.app.ui

import android.text.InputType
import android.view.View
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.RatingBar
import org.json.JSONObject
import pg.mcxus.app.MainActivity
import pg.mcxus.app.ui.Ui.dp
import pg.mcxus.app.util.Format
import pg.mcxus.app.util.Images

/** My orders, as buyer or seller. */
class OrdersScreen(main: MainActivity, private val asSeller: Boolean = false) : Screen(main) {
    override val title = "Orders"
    private lateinit var list: LinearLayout

    override fun build(): View {
        val ctx = main
        list = Ui.column(ctx, 0)
        return Ui.scroll(ctx, Ui.column(ctx, 14,
            Ui.row(ctx,
                Ui.weight(Ui.button(ctx, "Buying", primary = !asSeller) { main.openTab(OrdersScreen(main, false)) }),
                Ui.weight(Ui.button(ctx, "Selling", primary = asSeller) { main.openTab(OrdersScreen(main, true)) }),
            ),
            list,
        ))
    }

    override fun load() {
        launch {
            val orders = api.list("/v1/orders?as=${if (asSeller) "seller" else "buyer"}").objects()
            if (orders.isEmpty()) list.addView(Ui.muted(main, "No orders yet."))
            orders.forEach { o ->
                list.addView(Ui.card(main,
                    Ui.text(main, o.str("title"), bold = true),
                    Ui.text(main, Format.kina(o.str("amount")), color = Ui.GREEN),
                    Ui.muted(main, Format.orderStatus(o.str("status"), asSeller)),
                    Ui.muted(main, Format.dateTime(o.str("created_at"))),
                ) { main.show(OrderScreen(main, o.str("id"))) })
            }
        }
    }
}

/** One order with the actions allowed for me right now. Screenshots are blocked (handover PIN). */
class OrderScreen(main: MainActivity, private val orderId: String) : Screen(main) {
    override val title = "Order"
    override val secure = true
    private lateinit var body: LinearLayout

    override fun build(): View {
        body = Ui.column(main, 14)
        return Ui.scroll(main, body)
    }

    override fun load() {
        launch { render(api.obj("/v1/orders/$orderId")) }
    }

    private fun render(o: JSONObject) {
        val ctx = main
        body.removeAllViews()
        val asSeller = o.str("seller_id") == session.userId
        val status = o.str("status")
        body.addView(Ui.title(ctx, o.str("title")))
        body.addView(Ui.text(ctx, "${Format.kina(o.str("amount"))} · qty ${o.optInt("quantity", 1)}", 17f, bold = true,
            color = Ui.GREEN))
        body.addView(Ui.chip(ctx, Format.orderStatus(status, asSeller)))
        if (status == "FUNDED") {
            val mins = Format.minutesUntil(o.str("accept_deadline"))
            if (mins != null && mins >= 0) body.addView(Ui.muted(ctx, "Seller has $mins min left to accept."))
        }
        if (status == "DISPATCHED") body.addView(Ui.muted(ctx, "Auto-release on ${Format.dateTime(o.str("auto_release_at"))} unless disputed."))
        if (o.str("closed_at").isNotEmpty()) {
            body.addView(Ui.muted(ctx, "Fee ${Format.kina(o.str("fee_charged"))} · buyer refunded " +
                "${Format.kina(o.str("buyer_refunded"))} · seller paid ${Format.kina(o.str("seller_paid"))}"))
        }
        if (asSeller) sellerActions(status) else buyerActions(status)
        body.addView(Ui.button(ctx, "Refresh", primary = false) { load() })
    }

    private fun buyerActions(status: String) {
        val ctx = main
        when (status) {
            "CREATED" -> {
                body.addView(Ui.button(ctx, "Pay with Stars") { act("pay") })
                body.addView(Ui.button(ctx, "Cancel (free before paying)", primary = false) { act("cancel", confirm = "Cancel this order?") })
            }
            "FUNDED", "ACCEPTED", "DISPATCHED" -> {
                showPin()
                if (status != "FUNDED") {
                    body.addView(Ui.button(ctx, "I received the item — pay the seller") {
                        act("confirm-receipt", confirm = "Only confirm if you have the item. The seller gets the Stars now.")
                    })
                    body.addView(Ui.button(ctx, "Report a problem (dispute)", primary = false) { dispute() })
                }
                if (status != "DISPATCHED") {
                    body.addView(Ui.button(ctx, "Cancel order", primary = false) {
                        act("cancel", confirm = "Cancelling after paying costs a 5% fee (minimum K2). Cancel anyway?")
                    })
                }
            }
            "RELEASED", "RESOLVED" -> rate()
        }
    }

    private fun showPin() {
        val ctx = main
        val pin = session.pins[orderId]
        body.addView(Ui.label(ctx, "Handover PIN — show this only when you receive the item"))
        if (pin == null) {
            body.addView(Ui.button(ctx, "Show handover PIN", primary = false) {
                launch {
                    session.pins[orderId] = api.post("/v1/orders/$orderId/pin").str("handover_pin")
                    load()
                }
            })
            return
        }
        val size = ctx.dp(200)
        body.addView(ImageView(ctx).apply {
            setImageBitmap(Images.qr(Format.handoverQr(orderId, pin), size))
            layoutParams = LinearLayout.LayoutParams(size, size)
        })
        body.addView(Ui.text(ctx, pin.chunked(3).joinToString(" "), 30f, bold = true))
    }

    private fun sellerActions(status: String) {
        val ctx = main
        when (status) {
            "FUNDED" -> {
                body.addView(Ui.button(ctx, "Accept order") { act("accept") })
                body.addView(Ui.button(ctx, "Reject (no penalty within 20 min)", primary = false) { act("reject") })
            }
            "ACCEPTED", "DISPATCHED" -> {
                val pin = Ui.input(ctx, "Buyer's 6-digit PIN", InputType.TYPE_CLASS_NUMBER)
                body.addView(Ui.label(ctx, "At handover, enter the buyer's PIN to receive your Stars"))
                body.addView(pin)
                body.addView(Ui.button(ctx, "Confirm handover") {
                    act("handover", JSONObject().put("pin", pin.text.toString().trim()))
                })
                if (status == "ACCEPTED") {
                    body.addView(Ui.button(ctx, "Mark as sent (dispatched)", primary = false) { act("dispatch") })
                    body.addView(Ui.button(ctx, "Cancel order", primary = false) {
                        act("cancel", confirm = "Cancelling more than 25 minutes after payment costs you a 5% fee. Cancel?")
                    })
                }
            }
        }
    }

    private fun act(action: String, payload: JSONObject? = null, confirm: String? = null) {
        val run = {
            launch {
                val r = api.post("/v1/orders/$orderId/$action", payload)
                if (action == "pay") session.pins[orderId] = r.str("handover_pin")
                main.toast("Done")
                load()
            }
        }
        if (confirm != null) main.confirm(confirm) { run() } else run()
    }

    private fun dispute() {
        val reason = Ui.input(main, "What went wrong?")
        android.app.AlertDialog.Builder(main).setTitle("Report a problem").setView(reason)
            .setPositiveButton("Send") { _, _ ->
                act("dispute", JSONObject().put("reason", reason.text.toString().ifBlank { "Problem with the item" }))
            }.setNegativeButton("Cancel", null).show()
    }

    private fun rate() {
        val ctx = main
        val stars = RatingBar(ctx).apply { numStars = 5; stepSize = 1f; rating = 5f }
        val comment = Ui.input(ctx, "Comment (optional)")
        body.addView(Ui.label(ctx, "Rate the seller"))
        body.addView(LinearLayout(ctx).apply { addView(stars) })
        body.addView(comment)
        body.addView(Ui.button(ctx, "Send rating") {
            launch {
                api.post("/v1/orders/$orderId/review",
                    JSONObject().put("stars", stars.rating.toInt()).put("comment", comment.text.toString()))
                main.toast("Thanks for rating")
            }
        })
    }
}

package pg.mcxus.app.ui

import android.app.AlertDialog
import android.view.View
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import org.json.JSONObject
import pg.mcxus.app.MainActivity
import pg.mcxus.app.util.Format
import pg.mcxus.app.util.Images

/** One listing: photos, details, seller, buy (buyers) or manage (its seller). */
class ListingScreen(main: MainActivity, private val listingId: String) : Screen(main) {
    override val title = "Item"
    private lateinit var body: LinearLayout

    override fun build(): View {
        body = Ui.column(main, 14)
        return Ui.scroll(main, body)
    }

    override fun load() {
        launch {
            val item = api.obj("/v1/listings/$listingId")
            render(item)
        }
    }

    private fun render(item: JSONObject) {
        val ctx = main
        body.removeAllViews()
        val photos = item.getJSONArray("photos").objects()
        if (photos.isNotEmpty()) {
            val strip = Ui.row(ctx)
            photos.forEach { p ->
                val img = Ui.image(ctx, 220)
                Images.into(main.scope, img, session.server.trimEnd('/') + p.str("url"))
                strip.addView(img)
            }
            body.addView(HorizontalScrollView(ctx).apply { addView(strip) })
        }
        val seller = item.getJSONObject("seller")
        val mine = seller.str("id") == session.userId
        val place = listOf(item.str("suburb"), item.str("district"), item.str("province")).filter { it.isNotEmpty() }
        val delivery = (0 until item.getJSONArray("delivery_options").length())
            .joinToString(", ") { Format.delivery(item.getJSONArray("delivery_options").getString(it)) }
        body.addView(Ui.title(ctx, item.str("title")))
        body.addView(Ui.text(ctx, Format.price(item.str("price")), 18f, bold = true, color = Ui.GREEN))
        body.addView(Ui.muted(ctx, "${item.optInt("quantity_available")} available · ${Format.condition(item.str("condition"))}" +
            " · ${item.str("status").replace('_', ' ')}"))
        body.addView(Ui.muted(ctx, "📍 ${place.joinToString(", ")}"))
        body.addView(Ui.muted(ctx, "Delivery: $delivery"))
        if (item.str("description").isNotEmpty()) body.addView(Ui.text(ctx, item.str("description")))
        body.addView(Ui.card(ctx,
            Ui.text(ctx, seller.str("name"), bold = true),
            Ui.row(ctx, Ui.chip(ctx, Format.badge(seller.str("badge"))),
                Ui.muted(ctx, "   " + if (seller.str("rating").isNotEmpty())
                    "★ ${seller.str("rating")} (${seller.optInt("reviews")} reviews)" else "No reviews yet")),
        ))

        if (mine) {
            body.addView(Ui.label(ctx, "Your listing"))
            body.addView(Ui.button(ctx, "Add photo (up to 5)") {
                PhotoUploader(main, listingId) { load() }.choose()
            })
            val status = item.str("status")
            if (status == "active" || status == "sold_out") {
                body.addView(Ui.button(ctx, "Pause listing", primary = false) { setStatus("paused") })
            } else if (status == "paused") {
                body.addView(Ui.button(ctx, "Put back on sale") { setStatus("active") })
            }
            body.addView(Ui.button(ctx, "Close listing (stop selling)", primary = false) {
                main.confirm("Close this listing for good?") { setStatus("closed") }
            })
            return
        }
        if (item.str("status") != "active") {
            body.addView(Ui.text(ctx, "Sold out", 16f, bold = true, color = Ui.RED))
        } else {
            val qty = Ui.numberInput(ctx, "Quantity", "1")
            body.addView(Ui.label(ctx, "Quantity"))
            body.addView(qty)
            body.addView(Ui.button(ctx, "Buy with Stars") {
                buy(item, qty.text.toString().toIntOrNull() ?: 1)
            })
            body.addView(Ui.muted(ctx, "Your Stars are held safely in escrow and only go to the seller after you receive " +
                "the item. The first buyer to pay gets it."))
        }
        body.addView(Ui.button(ctx, "Report this listing", primary = false) { report() })
    }

    private fun buy(item: JSONObject, quantity: Int) {
        main.confirm("Pay ${Format.price(item.str("price"))} × $quantity from your Stars wallet?", "Pay") {
            launch {
                val order = api.post("/v1/listings/$listingId/buy", JSONObject().put("quantity", quantity), idempotent = true)
                val orderId = order.str("id")
                val paid = api.post("/v1/orders/$orderId/pay")
                session.pins[orderId] = paid.str("handover_pin")
                main.toast("Paid. Stars are in escrow.")
                main.show(OrderScreen(main, orderId))
            }
        }
    }

    private fun setStatus(status: String) = launch {
        api.post("/v1/listings/$listingId/status", JSONObject().put("status", status))
        main.toast("Listing ${status.replace('_', ' ')}")
        load()
    }

    private fun report() {
        val reasons = arrayOf("prohibited", "scam", "wrong_category", "offensive", "other")
        val labels = arrayOf("Prohibited item", "Looks like a scam", "Wrong category", "Offensive", "Other")
        AlertDialog.Builder(main).setTitle("Why are you reporting it?").setItems(labels) { _, i ->
            launch {
                api.post("/v1/listings/$listingId/report", JSONObject().put("reason", reasons[i]))
                main.alert("Thank you. A moderator will check this listing.")
            }
        }.show()
    }
}

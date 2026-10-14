package pg.mcxus.app.chat

import org.json.JSONObject

/**
 * What goes inside an encrypted message. Only the two phones ever see this JSON.
 *  {"t":"text","body":"…"}
 *  {"t":"listing","id":"…","title":"…","price":"120.00","thumb":"/media/…"}
 *  {"t":"order","id":"…","title":"…","amount":"120.00"}
 *  {"t":"system","body":"…"}   (written locally only, never sent)
 */
object Payload {
    fun text(body: String): String = JSONObject().put("t", "text").put("body", body).toString()

    fun listing(id: String, title: String, price: String, thumb: String): String =
        JSONObject().put("t", "listing").put("id", id).put("title", title).put("price", price).put("thumb", thumb).toString()

    fun order(id: String, title: String, amount: String): String =
        JSONObject().put("t", "order").put("id", id).put("title", title).put("amount", amount).toString()

    fun system(body: String): String = JSONObject().put("t", "system").put("body", body).toString()

    fun parse(raw: String): JSONObject = try {
        JSONObject(raw)
    } catch (e: Exception) {
        JSONObject().put("t", "text").put("body", raw)
    }

    /** One-line preview for the chat list. */
    fun preview(raw: String): String {
        val p = parse(raw)
        return when (p.optString("t")) {
            "listing" -> "🛍 " + p.optString("title")
            "order" -> "★ Order · K" + p.optString("amount")
            else -> p.optString("body")
        }
    }
}

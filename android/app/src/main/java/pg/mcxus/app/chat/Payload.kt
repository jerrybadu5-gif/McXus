package pg.mcxus.app.chat

import org.json.JSONObject

/**
 * What goes inside an encrypted message. Only the two phones ever see this JSON.
 *  {"t":"text","body":"…"}
 *  {"t":"listing","id":"…","title":"…","price":"120.00","thumb":"/media/…"}
 *  {"t":"order","id":"…","title":"…","amount":"120.00"}
 *  {"t":"location","latitude":"-6.72900","longitude":"146.99700","address":"Eriku market gate"}
 *  {"t":"system","body":"…"}   (written locally only, never sent)
 */
object Payload {
    fun text(body: String): String = JSONObject().put("t", "text").put("body", body).toString()

    fun listing(id: String, title: String, price: String, thumb: String): String =
        JSONObject().put("t", "listing").put("id", id).put("title", title).put("price", price).put("thumb", thumb).toString()

    fun order(id: String, title: String, amount: String): String =
        JSONObject().put("t", "order").put("id", id).put("title", title).put("amount", amount).toString()

    /** A meeting / delivery point shared in the chat (end-to-end encrypted: the server never sees it). */
    fun location(place: pg.mcxus.app.util.Place): String = place.toJson().put("t", "location").toString()

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
            "location" -> "📍 " + p.optString("address").ifBlank { "Location" }
            else -> p.optString("body")
        }
    }
}

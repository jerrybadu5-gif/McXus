package pg.mcxus.app.chat

import org.json.JSONObject

/**
 * What goes inside an encrypted message. Only the two phones ever see this JSON.
 *  {"t":"text","body":"…"}
 *  {"t":"listing","id":"…","title":"…","price":"120.00","thumb":"/media/…"}
 *  {"t":"order","id":"…","title":"…","amount":"120.00"}
 *  {"t":"dispute","order":"…","title":"…","body":"The buyer opened a dispute: …"}   (tap opens the dispute)
 *  {"t":"location","latitude":"-6.72900","longitude":"146.99700","address":"Eriku market gate"}
 *  {"t":"image","blob":"…","key":"<base64>","sha":"…","w":1280,"h":960,"thumb":"<base64 tiny jpeg>","body":"caption"}
 *  {"t":"voice","blob":"…","key":"<base64>","sha":"…","ms":8200}
 *  {"t":"event","type":"added|removed|left","by":"<user>","users":["<user>",…]}   (server notice in groups)
 *  {"t":"system","body":"…"}   (written locally only, never sent)
 */
object Payload {
    fun text(body: String): String = JSONObject().put("t", "text").put("body", body).toString()

    fun listing(id: String, title: String, price: String, thumb: String): String =
        JSONObject().put("t", "listing").put("id", id).put("title", title).put("price", price).put("thumb", thumb).toString()

    fun order(id: String, title: String, amount: String): String =
        JSONObject().put("t", "order").put("id", id).put("title", title).put("amount", amount).toString()

    /** News about a dispute on an order, sent by the party who acted, so the other sees it in the chat. */
    fun dispute(orderId: String, title: String, body: String): String =
        JSONObject().put("t", "dispute").put("order", orderId).put("title", title).put("body", body).toString()

    /** A meeting / delivery point shared in the chat (end-to-end encrypted: the server never sees it). */
    fun location(place: pg.mcxus.app.util.Place): String = place.toJson().put("t", "location").toString()

    fun image(blob: String, key: String, sha: String, w: Int, h: Int, thumb: String, caption: String): String =
        JSONObject().put("t", "image").put("blob", blob).put("key", key).put("sha", sha).put("w", w).put("h", h)
            .put("thumb", thumb).put("body", caption).toString()

    fun voice(blob: String, key: String, sha: String, ms: Long): String =
        JSONObject().put("t", "voice").put("blob", blob).put("key", key).put("sha", sha).put("ms", ms).toString()

    fun system(body: String): String = JSONObject().put("t", "system").put("body", body).toString()

    fun parse(raw: String): JSONObject = try {
        JSONObject(raw)
    } catch (e: Exception) {
        JSONObject().put("t", "text").put("body", raw)
    }

    fun formatDuration(ms: Long): String {
        val s = (ms / 1000).coerceAtLeast(0)
        return "%d:%02d".format(s / 60, s % 60)
    }

    /** One-line preview for the chat list. */
    fun preview(raw: String): String {
        val p = parse(raw)
        return when (p.optString("t")) {
            "listing" -> "🛍 " + p.optString("title")
            "order" -> "★ Order · K" + p.optString("amount")
            "dispute" -> "⚖ " + p.optString("body").ifBlank { "Dispute update" }
            "location" -> "📍 " + p.optString("address").ifBlank { "Location" }
            "image" -> "📷 " + p.optString("body").ifBlank { "Photo" }
            "voice" -> "🎤 Voice message " + formatDuration(p.optLong("ms"))
            "event" -> when (p.optString("type")) {
                "added" -> "New members added"
                "removed" -> "Members removed"
                "left" -> "Someone left the group"
                else -> "Group updated"
            }
            else -> p.optString("body")
        }
    }
}

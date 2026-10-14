package pg.mcxus.app.util

import java.time.Duration
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** Display helpers. Pure Kotlin so they are unit-tested on the JVM. */
object Format {
    private val PNG = ZoneId.of("Pacific/Port_Moresby")
    private val DATE_TIME = DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm")

    /** "120.00" -> "K120.00". Amounts arrive as exact strings from the server; never parsed to float. */
    fun kina(amount: String): String = if (amount.startsWith("-")) "-K${amount.drop(1)}" else "K$amount"

    /** "120.00" -> "K120.00 · 120.00 Stars" (1 Star = K1). */
    fun price(amount: String): String = "${kina(amount)} · $amount Stars"

    /** What the user typed -> the server's 2-decimal string: "120" -> "120.00", "12.5" -> "12.50". Null if invalid. */
    fun amount(raw: String): String? {
        val t = raw.trim().removePrefix("K").removePrefix("k")
        if (!Regex("""^\d{1,12}(\.\d{0,2})?$""").matches(t)) return null
        val parts = t.split(".")
        return "${parts[0]}.${(parts.getOrNull(1) ?: "").padEnd(2, '0')}"
    }

    fun dateTime(iso: String?): String =
        if (iso.isNullOrEmpty() || iso == "null") "" else OffsetDateTime.parse(iso).atZoneSameInstant(PNG).format(DATE_TIME)

    /** Minutes left until [iso] (negative if passed). */
    fun minutesUntil(iso: String?, now: OffsetDateTime = OffsetDateTime.now()): Long? =
        if (iso.isNullOrEmpty() || iso == "null") null else Duration.between(now, OffsetDateTime.parse(iso)).toMinutes()

    fun orderStatus(status: String, asSeller: Boolean): String = when (status) {
        "CREATED" -> if (asSeller) "Waiting for the buyer to pay" else "Not paid yet"
        "FUNDED" -> if (asSeller) "Paid — accept or reject within 20 minutes" else "Paid — waiting for the seller (20 min)"
        "ACCEPTED" -> "Accepted — arrange delivery or meet-up"
        "DISPATCHED" -> "On the way"
        "DISPUTED" -> "In dispute — a mediator will decide"
        "RELEASED" -> "Completed — Stars paid to the seller"
        "RESOLVED" -> "Dispute decided"
        "CANCELLED" -> "Cancelled"
        "SELLER_REJECTED" -> "Seller declined — buyer refunded"
        "AUTO_REJECTED" -> "Seller did not respond — buyer refunded"
        "SELLER_CANCELLED" -> "Seller cancelled — buyer refunded"
        else -> status
    }

    fun badge(badge: String): String = when (badge) {
        "new_seller" -> "New seller"
        "bronze" -> "Bronze seller"
        "silver" -> "Silver seller"
        "gold" -> "Gold seller"
        "verified_store" -> "Verified store"
        "caution" -> "Caution"
        else -> badge
    }

    fun condition(c: String): String = when (c) {
        "new" -> "New"
        "like_new" -> "Like new"
        "good" -> "Good"
        "fair" -> "Fair"
        "not_applicable" -> "—"
        else -> c
    }

    fun delivery(d: String): String = when (d) {
        "meetup" -> "Meet-up"
        "pickup" -> "Pickup"
        "seller_delivers" -> "Seller delivers"
        "courier" -> "Courier"
        else -> d
    }

    /** Text for the handover QR code: the seller's app (M3) will scan it; for now the seller types the PIN. */
    fun handoverQr(orderId: String, pin: String): String = "mcxus:handover:$orderId:$pin"
}

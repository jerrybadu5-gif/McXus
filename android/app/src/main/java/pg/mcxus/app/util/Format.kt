package pg.mcxus.app.util

import java.time.Duration
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

/** Display helpers. Pure Kotlin so they are unit-tested on the JVM. */
object Format {
    val PNG: ZoneId = ZoneId.of("Pacific/Port_Moresby")
    private val DATE_TIME = DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm")
    private val TIME = DateTimeFormatter.ofPattern("HH:mm")
    private val WEEKDAY = DateTimeFormatter.ofPattern("EEE", java.util.Locale.ENGLISH)
    private val SHORT_DATE = DateTimeFormatter.ofPattern("dd/MM/yy")

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
        "DISPUTED" -> "In dispute — Stars are held until it is settled"
        "RELEASED" -> "Completed — Stars paid to the seller"
        "RESOLVED" -> "Dispute settled"
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

    /** Chat list time: "10:42" today, "Yesterday", weekday this week, else "14/10/26". */
    fun chatTime(epochMillis: Long, now: ZonedDateTime = ZonedDateTime.now(PNG)): String {
        if (epochMillis <= 0) return ""
        val t = Instant.ofEpochMilli(epochMillis).atZone(PNG)
        val days = ChronoUnit.DAYS.between(t.toLocalDate(), now.toLocalDate())
        return when {
            days <= 0L -> t.format(TIME)
            days == 1L -> "Yesterday"
            days < 7L -> t.format(WEEKDAY)
            else -> t.format(SHORT_DATE)
        }
    }

    /** Bubble time "10:42". */
    fun clock(epochMillis: Long): String = Instant.ofEpochMilli(epochMillis).atZone(PNG).format(TIME)

    /** Text for the handover QR code: the seller's app (M3) will scan it; for now the seller types the PIN. */
    fun handoverQr(orderId: String, pin: String): String = "mcxus:handover:$orderId:$pin"
}

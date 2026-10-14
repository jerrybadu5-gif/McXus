package pg.mcxus.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import pg.mcxus.app.net.Api
import pg.mcxus.app.util.Format
import java.time.OffsetDateTime

class FormatTest {
    @Test
    fun kinaAndStars() {
        assertEquals("K120.00", Format.kina("120.00"))
        assertEquals("-K5.00", Format.kina("-5.00"))
        assertEquals("K120.00 · 120.00 Stars", Format.price("120.00"))
    }

    @Test
    fun amountParsing() {
        assertEquals("120.00", Format.amount("120"))
        assertEquals("12.50", Format.amount("12.5"))
        assertEquals("12.05", Format.amount(" K12.05 "))
        assertEquals("7.00", Format.amount("7."))
        assertNull(Format.amount("12.345"))
        assertNull(Format.amount("-5"))
        assertNull(Format.amount("abc"))
        assertNull(Format.amount(""))
    }

    @Test
    fun datesShownInPortMoresbyTime() {
        assertEquals("14/10/2026 10:30", Format.dateTime("2026-10-14T00:30:00+00:00"))
        assertEquals("", Format.dateTime(null))
        val now = OffsetDateTime.parse("2026-10-14T00:00:00Z")
        assertEquals(20L, Format.minutesUntil("2026-10-14T00:20:00+00:00", now))
    }

    @Test
    fun statusLabelsDependOnSide() {
        assertEquals("Paid — accept or reject within 20 minutes", Format.orderStatus("FUNDED", asSeller = true))
        assertEquals("Paid — waiting for the seller (20 min)", Format.orderStatus("FUNDED", asSeller = false))
        assertEquals("Seller did not respond — buyer refunded", Format.orderStatus("AUTO_REJECTED", asSeller = false))
    }

    @Test
    fun handoverQrText() {
        assertEquals("mcxus:handover:abc:123456", Format.handoverQr("abc", "123456"))
    }
}

class ApiErrorTest {
    @Test
    fun appErrorShape() {
        val e = Api.parseError(409, """{"error":{"code":"sold_out","message":"Sorry, someone else has just bought this item"}}""")
        assertEquals(409, e.status)
        assertEquals("sold_out", e.code)
        assertEquals("Sorry, someone else has just bought this item", e.message)
    }

    @Test
    fun validationErrorShape() {
        val e = Api.parseError(422, """{"detail":[{"loc":["body","price"],"msg":"Input should be greater than 0"}]}""")
        assertEquals("invalid_input", e.code)
        assertEquals("price: Input should be greater than 0", e.message)
    }

    @Test
    fun nonJsonBody() {
        val e = Api.parseError(502, "<html>Bad gateway</html>")
        assertEquals("Server error (502)", e.message)
    }
}

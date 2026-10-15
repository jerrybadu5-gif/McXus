package pg.mcxus.app

import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import pg.mcxus.app.chat.Payload

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PayloadTest {
    @Test
    fun disputeCardCarriesTheOrderAndPreviewsInTheChatList() {
        val raw = Payload.dispute("order-1", "Solar lamp", "Offer: buyer gets back K40.00")
        val p = Payload.parse(raw)
        assertEquals("dispute", p.getString("t"))
        assertEquals("order-1", p.getString("order"))
        assertEquals("⚖ Offer: buyer gets back K40.00", Payload.preview(raw))
    }
}

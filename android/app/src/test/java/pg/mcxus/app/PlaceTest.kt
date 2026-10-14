package pg.mcxus.app

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import pg.mcxus.app.chat.Payload
import pg.mcxus.app.util.Place

class PlaceTest {
    @Test
    fun coordinatesAreFiveDecimalsLikeTheServer() {
        val p = Place.of(-6.729, 146.997, "Eriku market gate")
        assertEquals("-6.72900", p.latitude)
        assertEquals("146.99700", p.longitude)
        assertTrue(p.hasPoint && p.inPng)
    }

    @Test
    fun pngBounds() {
        assertTrue(Place.of(-9.4438, 147.1803).inPng) // Port Moresby
        assertTrue(Place.of(-6.2, 155.5).inPng) // Bougainville
        assertFalse(Place.of(-33.86, 151.2).inPng) // Sydney
        assertFalse(Place(address = "Eriku").inPng)
    }

    @Test
    fun readsListingAndOrderJson() {
        val listing = JSONObject("""{"latitude":"-6.72900","longitude":"146.99700","address":"Eriku market gate"}""")
        assertEquals(Place("-6.72900", "146.99700", "Eriku market gate"), Place.from(listing))
        val order = JSONObject("""{"delivery_latitude":null,"delivery_longitude":null,"delivery_address":"Taraka gate 2"}""")
        assertEquals(Place(null, null, "Taraka gate 2"), Place.from(order, "delivery_"))
        assertNull(Place.from(JSONObject("""{"delivery_latitude":null,"delivery_longitude":null,"delivery_address":""}"""), "delivery_"))
    }

    @Test
    fun locationMessageRoundTrip() {
        val raw = Payload.location(Place.of(-6.729, 146.997, "Eriku market gate"))
        val back = Place.from(Payload.parse(raw))
        assertEquals("-6.72900", back!!.latitude)
        assertEquals("📍 Eriku market gate", Payload.preview(raw))
    }
}

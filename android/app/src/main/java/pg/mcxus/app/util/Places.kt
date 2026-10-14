package pg.mcxus.app.util

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Geocoder
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.net.Uri
import android.os.Build
import android.os.CancellationSignal
import android.os.Looper
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject
import java.util.Locale
import kotlin.coroutines.resume

/**
 * A place where people meet or deliver: GPS point first (so phones can navigate to it), address/landmark second
 * (so people can recognise it: "Eriku market gate, near BSP"). Coordinates are kept as 5-decimal strings (~1 m),
 * exactly as the server stores them.
 */
data class Place(val latitude: String? = null, val longitude: String? = null, val address: String = "") {
    val hasPoint: Boolean get() = latitude != null && longitude != null
    val isEmpty: Boolean get() = !hasPoint && address.isBlank()

    /** PNG and its islands: about 0–12°S, 140–160°E (same bounds as the server). */
    val inPng: Boolean get() = hasPoint && latitude!!.toDouble() in -12.0..0.0 && longitude!!.toDouble() in 140.0..160.0

    fun coordinates(): String = if (hasPoint) "$latitude, $longitude" else ""

    fun toJson(): JSONObject = JSONObject()
        .put("latitude", latitude ?: JSONObject.NULL)
        .put("longitude", longitude ?: JSONObject.NULL)
        .put("address", address.trim())

    companion object {
        fun of(lat: Double, lng: Double, address: String = "") = Place(fmt(lat), fmt(lng), address)

        fun fmt(v: Double): String = String.format(Locale.US, "%.5f", v)

        /** From an API object with latitude/longitude/address (or a prefix, e.g. "delivery_"). */
        fun from(o: JSONObject?, prefix: String = "", addressKey: String = "${prefix}address"): Place? {
            if (o == null) return null
            val lat = o.opt("${prefix}latitude").takeIf { it != null && it != JSONObject.NULL }?.toString()
            val lng = o.opt("${prefix}longitude").takeIf { it != null && it != JSONObject.NULL }?.toString()
            val p = Place(lat, lng, o.optString(addressKey, ""))
            return if (p.isEmpty) null else p
        }
    }
}

object Places {
    /** Port Moresby: where the map opens when nothing better is known. */
    val DEFAULT = Place.of(-9.44380, 147.18030)

    fun hasPermission(context: Context): Boolean =
        context.checkSelfPermission(android.Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            context.checkSelfPermission(android.Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    fun locationOn(context: Context): Boolean {
        val lm = context.getSystemService(LocationManager::class.java) ?: return false
        return lm.isProviderEnabled(LocationManager.GPS_PROVIDER) || lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER)
    }

    /**
     * The phone's current position, using only Android's own LocationManager (no Google Play services, so it
     * works on any Android 8+ phone). Tries GPS, then the network; falls back to the last known fix.
     */
    @SuppressLint("MissingPermission")
    suspend fun current(context: Context, timeoutMs: Long = 25_000): Location? {
        if (!hasPermission(context)) return null
        val lm = context.getSystemService(LocationManager::class.java) ?: return null
        val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER).filter { lm.isProviderEnabled(it) }
        for (provider in providers) {
            val fix = withTimeoutOrNull(timeoutMs / providers.size) { single(lm, provider) }
            if (fix != null) return fix
        }
        return providers.mapNotNull { lm.getLastKnownLocation(it) }.maxByOrNull { it.time }
    }

    @SuppressLint("MissingPermission")
    private suspend fun single(lm: LocationManager, provider: String): Location? = suspendCancellableCoroutine { cont ->
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val cancel = CancellationSignal()
            cont.invokeOnCancellation { cancel.cancel() }
            lm.getCurrentLocation(provider, cancel, { it.run() }) { if (cont.isActive) cont.resume(it) }
        } else {
            val listener = object : LocationListener {
                override fun onLocationChanged(location: Location) {
                    lm.removeUpdates(this)
                    if (cont.isActive) cont.resume(location)
                }

                @Deprecated("Deprecated in Java")
                override fun onStatusChanged(provider: String?, status: Int, extras: android.os.Bundle?) = Unit
                override fun onProviderEnabled(provider: String) = Unit
                override fun onProviderDisabled(provider: String) = Unit
            }
            cont.invokeOnCancellation { lm.removeUpdates(listener) }
            lm.requestLocationUpdates(provider, 0L, 0f, listener, Looper.getMainLooper())
        }
    }

    /** Best-effort street/suburb name for a point (often empty in PNG; the person can always type a landmark). */
    @Suppress("DEPRECATION")
    suspend fun describe(context: Context, lat: Double, lng: Double): String = withContext(Dispatchers.IO) {
        if (!Geocoder.isPresent()) return@withContext ""
        runCatching {
            Geocoder(context, Locale.ENGLISH).getFromLocation(lat, lng, 1)?.firstOrNull()?.let { a ->
                listOfNotNull(a.thoroughfare, a.subLocality, a.locality).distinct().joinToString(", ")
            }.orEmpty()
        }.getOrDefault("")
    }

    /** Open the point in the phone's maps app (Google Maps, OsmAnd, Maps.me…) for directions. */
    fun openInMaps(context: Context, place: Place, label: String = "Meet here") {
        val uri = if (place.hasPoint) {
            Uri.parse("geo:${place.latitude},${place.longitude}?q=${place.latitude},${place.longitude}(${Uri.encode(label)})")
        } else {
            Uri.parse("geo:0,0?q=${Uri.encode(place.address + ", Papua New Guinea")}")
        }
        val intent = Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (intent.resolveActivity(context.packageManager) != null) {
            context.startActivity(intent)
        } else {
            val web = if (place.hasPoint) "https://www.openstreetmap.org/?mlat=${place.latitude}&mlon=${place.longitude}#map=17/${place.latitude}/${place.longitude}"
            else "https://www.openstreetmap.org/search?query=${Uri.encode(place.address)}"
            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(web)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    }

    /** Straight-line distance in km between two points ("1.2 km away"). */
    fun distanceKm(a: Place, b: Place): Double? {
        if (!a.hasPoint || !b.hasPoint) return null
        val out = FloatArray(1)
        Location.distanceBetween(a.latitude!!.toDouble(), a.longitude!!.toDouble(), b.latitude!!.toDouble(), b.longitude!!.toDouble(), out)
        return out[0] / 1000.0
    }
}

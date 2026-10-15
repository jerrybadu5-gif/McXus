// The framework ExifInterface is reliable from Android 8 (our minSdk 26); this avoids an extra library.
@file:Suppress("ExifInterface")

package pg.mcxus.app.util

import android.content.ContentResolver
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Matrix
import android.media.ExifInterface
import android.net.Uri
import android.util.LruCache
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.qrcode.QRCodeWriter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

object Images {
    private val cache = object : LruCache<String, Bitmap>(16 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap) = value.byteCount
    }

    fun cached(url: String): Bitmap? = cache.get(url)

    /** Download a listing photo (memory-cached; the server also sends week-long cache headers). */
    suspend fun load(url: String): Bitmap? = cache.get(url) ?: withContext(Dispatchers.IO) {
        runCatching {
            val conn = URL(url).openConnection() as HttpURLConnection
            conn.connectTimeout = 15_000
            conn.readTimeout = 30_000
            try {
                conn.inputStream.use { BitmapFactory.decodeStream(it) }
            } finally {
                conn.disconnect()
            }
        }.getOrNull()?.also { cache.put(url, it) }
    }

    /**
     * Shrink a picked or camera photo before upload (saves mobile data): longest side about 1600 px,
     * JPEG quality 80, rotated upright. The server strips location data again and resizes to 1280 px.
     */
    fun prepareUpload(resolver: ContentResolver, uri: Uri, maxPx: Int = 1600, quality: Int = 80): ByteArray {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        resolver.openInputStream(uri).use { BitmapFactory.decodeStream(it, null, bounds) }
        var sample = 1
        while (bounds.outWidth / (sample * 2) >= maxPx || bounds.outHeight / (sample * 2) >= maxPx) sample *= 2
        val decoded = resolver.openInputStream(uri).use {
            BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample })
        } ?: throw IllegalArgumentException("That file is not a photo")
        val rotation = resolver.openInputStream(uri).use { stream ->
            if (stream == null) 0 else when (ExifInterface(stream).getAttributeInt(
                ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL,
            )) {
                ExifInterface.ORIENTATION_ROTATE_90 -> 90
                ExifInterface.ORIENTATION_ROTATE_180 -> 180
                ExifInterface.ORIENTATION_ROTATE_270 -> 270
                else -> 0
            }
        }
        val scale = minOf(1f, maxPx.toFloat() / maxOf(decoded.width, decoded.height))
        val matrix = Matrix().apply { postScale(scale, scale); postRotate(rotation.toFloat()) }
        val upright = Bitmap.createBitmap(decoded, 0, 0, decoded.width, decoded.height, matrix, true)
        return ByteArrayOutputStream().use { out ->
            upright.compress(Bitmap.CompressFormat.JPEG, quality, out)
            out.toByteArray()
        }
    }

    /** Width and height of a JPEG without decoding it fully. */
    fun size(jpeg: ByteArray): Pair<Int, Int> {
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size, o)
        return o.outWidth to o.outHeight
    }

    /** A tiny (about 1 KB) blurry preview that travels inside the encrypted message. */
    fun thumbnail(jpeg: ByteArray, px: Int = 32): ByteArray {
        val full = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size) ?: return ByteArray(0)
        val scale = px.toFloat() / maxOf(full.width, full.height)
        val small = Bitmap.createScaledBitmap(full, maxOf(1, (full.width * scale).toInt()), maxOf(1, (full.height * scale).toInt()), true)
        return ByteArrayOutputStream().use { out -> small.compress(Bitmap.CompressFormat.JPEG, 50, out); out.toByteArray() }
    }

    fun qr(text: String, sizePx: Int): Bitmap {
        val matrix = QRCodeWriter().encode(text, BarcodeFormat.QR_CODE, sizePx, sizePx, mapOf(EncodeHintType.MARGIN to 1))
        val pixels = IntArray(sizePx * sizePx) { i -> if (matrix.get(i % sizePx, i / sizePx)) Color.BLACK else Color.WHITE }
        return Bitmap.createBitmap(pixels, sizePx, sizePx, Bitmap.Config.RGB_565)
    }
}

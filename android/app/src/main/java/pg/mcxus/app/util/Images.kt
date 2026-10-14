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
import android.widget.ImageView
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.qrcode.QRCodeWriter
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

object Images {
    private val cache = object : LruCache<String, Bitmap>(16 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap) = value.byteCount
    }

    /** Load a listing photo into [view] (cached in memory; the server sends week-long cache headers). */
    fun into(scope: CoroutineScope, view: ImageView, url: String) {
        cache.get(url)?.let { view.setImageBitmap(it); return }
        view.tag = url
        scope.launch {
            val bitmap = withContext(Dispatchers.IO) {
                runCatching {
                    val conn = URL(url).openConnection() as HttpURLConnection
                    conn.connectTimeout = 15_000
                    conn.readTimeout = 30_000
                    conn.inputStream.use { BitmapFactory.decodeStream(it) }.also { conn.disconnect() }
                }.getOrNull()
            }
            if (bitmap != null) {
                cache.put(url, bitmap)
                if (view.tag == url) view.setImageBitmap(bitmap)
            }
        }
    }

    /**
     * Shrink a picked or camera photo before upload (saves mobile data): longest side about 1600 px,
     * JPEG quality 80, rotated upright. The server strips location data again and resizes to 1280 px.
     */
    fun prepareUpload(resolver: ContentResolver, uri: Uri, maxPx: Int = 1600): ByteArray {
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
            upright.compress(Bitmap.CompressFormat.JPEG, 80, out)
            out.toByteArray()
        }
    }

    fun qr(text: String, sizePx: Int): Bitmap {
        val matrix = QRCodeWriter().encode(text, BarcodeFormat.QR_CODE, sizePx, sizePx, mapOf(EncodeHintType.MARGIN to 1))
        val pixels = IntArray(sizePx * sizePx) { i -> if (matrix.get(i % sizePx, i / sizePx)) Color.BLACK else Color.WHITE }
        return Bitmap.createBitmap(pixels, sizePx, sizePx, Bitmap.Config.RGB_565)
    }
}

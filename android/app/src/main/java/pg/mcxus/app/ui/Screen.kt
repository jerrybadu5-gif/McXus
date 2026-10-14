package pg.mcxus.app.ui

import android.Manifest
import android.app.AlertDialog
import android.content.ContentValues
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import android.view.View
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import pg.mcxus.app.MainActivity
import pg.mcxus.app.util.Images

/** One screen. [build] creates the views; [load] fetches data (runs after the views are shown). */
abstract class Screen(val main: MainActivity) {
    abstract val title: String
    open val secure: Boolean = false
    open val showTabs: Boolean = true

    abstract fun build(): View
    open fun load() = Unit

    val api get() = main.api
    val session get() = main.session

    fun launch(block: suspend () -> Unit) = main.launch(block)
}

fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }

fun JSONObject.str(key: String): String = if (isNull(key)) "" else optString(key, "")

/** Gallery or camera -> shrink -> upload to /v1/listings/{id}/photos. */
class PhotoUploader(private val main: MainActivity, private val listingId: String, private val onUploaded: () -> Unit) {
    private var cameraUri: Uri? = null

    fun choose() {
        AlertDialog.Builder(main).setTitle("Add a photo")
            .setItems(arrayOf("Take photo", "Choose from gallery")) { _, which ->
                if (which == 0) camera() else gallery()
            }.show()
    }

    private fun gallery() {
        main.onActivityResultHandler = ::onResult
        @Suppress("DEPRECATION")
        main.startActivityForResult(Intent(Intent.ACTION_GET_CONTENT).setType("image/*"), REQ_GALLERY)
    }

    private fun camera() {
        val needsStorage = Build.VERSION.SDK_INT < Build.VERSION_CODES.Q &&
            main.checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED
        if (needsStorage) {
            main.onPermissionHandler = { granted -> if (granted) camera() else main.toast("Storage permission is needed for camera photos") }
            main.requestPermissions(arrayOf(Manifest.permission.WRITE_EXTERNAL_STORAGE), REQ_PERMISSION)
            return
        }
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, "mcxus_${System.currentTimeMillis()}.jpg")
            put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
        }
        cameraUri = main.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
        val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE).putExtra(MediaStore.EXTRA_OUTPUT, cameraUri)
        main.onActivityResultHandler = ::onResult
        @Suppress("DEPRECATION")
        main.startActivityForResult(intent, REQ_CAMERA)
    }

    private fun onResult(requestCode: Int, resultCode: Int, data: Intent?) {
        main.onActivityResultHandler = null
        if (resultCode != android.app.Activity.RESULT_OK) return
        val uri = when (requestCode) {
            REQ_GALLERY -> data?.data
            REQ_CAMERA -> cameraUri
            else -> null
        } ?: return
        main.toast("Uploading photo…")
        main.launch {
            val jpeg = withContext(Dispatchers.Default) { Images.prepareUpload(main.contentResolver, uri) }
            main.api.upload("/v1/listings/$listingId/photos", jpeg)
            main.toast("Photo added")
            onUploaded()
        }
    }

    companion object {
        const val REQ_GALLERY = 41
        const val REQ_CAMERA = 42
        const val REQ_PERMISSION = 43
    }
}

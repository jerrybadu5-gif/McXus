package pg.mcxus.app.ui

import android.text.InputType
import android.view.View
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import org.json.JSONArray
import org.json.JSONObject
import pg.mcxus.app.MainActivity
import pg.mcxus.app.util.Format

/** Create a listing. After saving, the listing page opens so the seller can add photos. */
class SellScreen(main: MainActivity) : Screen(main) {
    override val title = "Sell an item"

    private lateinit var titleIn: EditText
    private lateinit var descIn: EditText
    private lateinit var priceIn: EditText
    private lateinit var qtyIn: EditText
    private lateinit var categoryBox: LinearLayout
    private lateinit var subCategoryBox: LinearLayout
    private lateinit var placeBox: LinearLayout
    private lateinit var districtBox: LinearLayout
    private lateinit var suburbBox: LinearLayout
    private val deliveryChecks = mutableMapOf<String, CheckBox>()

    private var categoryId: Int? = null
    private var condition = "good"
    private var provinceId: Int? = null
    private var districtId: Int? = null
    private var suburbId: Int? = null

    override fun build(): View {
        val ctx = main
        titleIn = Ui.input(ctx, "Title, e.g. Solar lamp with phone charger")
        descIn = Ui.input(ctx, "Description",
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES)
        priceIn = Ui.numberInput(ctx, "Price in Kina, e.g. 120.00", decimal = true)
        qtyIn = Ui.numberInput(ctx, "How many?", "1")
        categoryBox = Ui.column(ctx, 0)
        subCategoryBox = Ui.column(ctx, 0)
        placeBox = Ui.column(ctx, 0)
        districtBox = Ui.column(ctx, 0)
        suburbBox = Ui.column(ctx, 0)
        val conditions = listOf("new", "like_new", "good", "fair", "not_applicable")
        val delivery = Ui.column(ctx, 0)
        listOf("meetup", "pickup", "seller_delivers", "courier").forEach { key ->
            val box = CheckBox(ctx).apply { text = Format.delivery(key); isChecked = key == "meetup" }
            deliveryChecks[key] = box
            delivery.addView(box)
        }
        return Ui.scroll(ctx, Ui.column(ctx, 16,
            Ui.label(ctx, "What are you selling?"), titleIn, descIn,
            Ui.label(ctx, "Category"), categoryBox, subCategoryBox,
            Ui.label(ctx, "Price (1 Star = K1)"), priceIn,
            Ui.label(ctx, "Quantity"), qtyIn,
            Ui.label(ctx, "Condition"),
            Ui.spinner(ctx, conditions, { Format.condition(it).replace("—", "Not applicable (food, services)") }) {
                condition = it
            }.apply { setSelection(2) },
            Ui.label(ctx, "Where is it?"), placeBox, districtBox, suburbBox,
            Ui.label(ctx, "Delivery"), delivery,
            Ui.button(ctx, "Save and add photos") { save() },
            Ui.muted(ctx, "Weapons, drugs, alcohol, tobacco, betel nut, protected wildlife and documents cannot be sold."),
        ))
    }

    override fun load() {
        launch {
            val cats = api.list("/v1/categories").objects()
            categoryBox.addView(Ui.spinner(main, cats, { it.str("name") }) { parent -> showSubCategories(parent) })
            val provinces = api.list("/v1/locations").objects()
            placeBox.addView(Ui.spinner(main, provinces, { it.str("name") }) { p -> onProvince(p.getInt("id")) })
        }
    }

    private fun showSubCategories(parent: JSONObject) {
        subCategoryBox.removeAllViews()
        val children = parent.optJSONArray("children") ?: JSONArray()
        if (children.length() == 0) {
            categoryId = parent.getInt("id")
            return
        }
        subCategoryBox.addView(Ui.spinner(main, children.objects(), { it.str("name") }) { categoryId = it.getInt("id") })
    }

    private fun onProvince(id: Int) {
        provinceId = id
        districtId = null
        suburbId = null
        districtBox.removeAllViews()
        suburbBox.removeAllViews()
        launch {
            val children = api.list("/v1/locations?parent_id=$id").objects()
            val districts = children.filter { it.str("level") == "district" }
            val suburbs = children.filter { it.str("level") == "suburb" } // NCD suburbs hang off the province
            if (districts.isNotEmpty()) {
                districtBox.addView(Ui.spinner(main, listOf<JSONObject?>(null) + districts,
                    { it?.str("name") ?: "District (optional)" }) { d -> onDistrict(d?.getInt("id"), suburbs) })
            }
            showSuburbs(suburbs)
        }
    }

    private fun onDistrict(id: Int?, provinceSuburbs: List<JSONObject>) {
        districtId = id
        if (id == null) return showSuburbs(provinceSuburbs)
        launch {
            val suburbs = api.list("/v1/locations?parent_id=$id").objects()
            showSuburbs(provinceSuburbs + suburbs)
        }
    }

    private fun showSuburbs(suburbs: List<JSONObject>) {
        suburbBox.removeAllViews()
        suburbId = null
        if (suburbs.isEmpty()) return
        suburbBox.addView(Ui.spinner(main, listOf<JSONObject?>(null) + suburbs,
            { it?.str("name") ?: "Suburb (optional)" }) { suburbId = it?.getInt("id") })
    }

    private fun save() {
        val price = Format.amount(priceIn.text.toString())
        if (titleIn.text.isBlank() || price == null || categoryId == null || provinceId == null) {
            main.alert("Please fill in the title, category, price (e.g. 120 or 120.50) and province.")
            return
        }
        val delivery = JSONArray().apply { deliveryChecks.filterValues { it.isChecked }.keys.forEach { put(it) } }
        val body = JSONObject()
            .put("title", titleIn.text.toString().trim())
            .put("description", descIn.text.toString().trim())
            .put("category_id", categoryId)
            .put("price", price)
            .put("quantity", qtyIn.text.toString().toIntOrNull() ?: 1)
            .put("condition", condition)
            .put("delivery_options", delivery)
            .put("province_id", provinceId)
            .put("district_id", districtId ?: JSONObject.NULL)
            .put("suburb_id", suburbId ?: JSONObject.NULL)
        launch {
            val listing = api.post("/v1/listings", body)
            main.toast("Listed! Now add photos.")
            main.show(ListingScreen(main, listing.str("id")))
        }
    }
}

package pg.mcxus.app.ui

import android.net.Uri
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import org.json.JSONObject
import pg.mcxus.app.MainActivity
import pg.mcxus.app.util.Format
import pg.mcxus.app.util.Images

/** Browse and search listings. */
class MarketScreen(main: MainActivity) : Screen(main) {
    override val title = "Market"

    private lateinit var query: EditText
    private lateinit var filters: LinearLayout
    private lateinit var results: LinearLayout
    private var category: String? = null
    private var provinceId: Int? = null
    private var offset = 0

    override fun build(): View {
        val ctx = main
        query = Ui.input(ctx, "Search, e.g. solar, bilum, phone")
        filters = Ui.column(ctx, 0)
        results = Ui.column(ctx, 0)
        return Ui.scroll(ctx, Ui.column(ctx, 14,
            query, filters,
            Ui.button(ctx, "Search") { search(reset = true) },
            results,
        ))
    }

    override fun load() {
        launch {
            val cats = api.list("/v1/categories").objects()
            val provinces = api.list("/v1/locations").objects()
            filters.addView(Ui.row(main,
                Ui.weight(Ui.spinner(main, listOf<JSONObject?>(null) + cats, { it?.str("name") ?: "All categories" }) {
                    category = it?.str("slug")
                }),
                Ui.weight(Ui.spinner(main, listOf<JSONObject?>(null) + provinces, { it?.str("name") ?: "All PNG" }) {
                    provinceId = it?.optInt("id")
                }),
            ))
            search(reset = true)
        }
    }

    private fun search(reset: Boolean) {
        if (reset) {
            offset = 0
            results.removeAllViews()
        }
        val params = buildList {
            val q = query.text.toString().trim()
            if (q.isNotEmpty()) add("q=" + Uri.encode(q))
            category?.let { add("category=$it") }
            provinceId?.let { add("province_id=$it") }
            add("limit=20")
            add("offset=$offset")
        }.joinToString("&")
        launch {
            val items = api.list("/v1/listings?$params").objects()
            if (items.isEmpty() && offset == 0) results.addView(Ui.muted(main, "Nothing found. Try fewer words or All PNG."))
            items.forEach { results.addView(card(it)) }
            offset += items.size
            if (items.size == 20) results.addView(Ui.button(main, "Load more", primary = false) {
                results.removeViewAt(results.childCount - 1)
                search(reset = false)
            })
        }
    }

    private fun card(item: JSONObject): View {
        val ctx = main
        val photo = Ui.image(ctx, 84)
        val photos = item.getJSONArray("photos")
        if (photos.length() > 0) Images.into(main.scope, photo, session.server.trimEnd('/') + photos.getJSONObject(0).str("thumb_url"))
        val seller = item.getJSONObject("seller")
        val place = listOf(item.str("suburb"), item.str("district"), item.str("province")).filter { it.isNotEmpty() }
        val info = Ui.column(ctx, 0,
            Ui.text(ctx, item.str("title"), 16f, bold = true),
            Ui.text(ctx, Format.price(item.str("price")), 15f, bold = true, color = Ui.GREEN),
            Ui.muted(ctx, place.joinToString(", ")),
            Ui.muted(ctx, "${seller.str("name")} · ${Format.badge(seller.str("badge"))}" +
                (if (seller.str("rating").isNotEmpty()) " · ★ ${seller.str("rating")}" else "")),
        )
        return Ui.card(ctx, Ui.row(ctx, photo, Ui.weight(info))) {
            main.show(ListingScreen(main, item.str("id")))
        }
    }
}

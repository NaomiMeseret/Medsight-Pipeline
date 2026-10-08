import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st


BASE_DIR = Path(__file__).parent
MESSAGES_DIR = BASE_DIR / "data" / "raw" / "telegram_messages"
YOLO_CSV = BASE_DIR / "data" / "processed" / "yolo_detections.csv"
IMAGE_DIR = BASE_DIR / "data" / "raw" / "images"

STOP_WORDS = {
    "and",
    "are",
    "birr",
    "call",
    "cosmetics",
    "delivery",
    "fees",
    "from",
    "ground",
    "high",
    "lobelia",
    "monday",
    "open",
    "option",
    "pharmacy",
    "plaza",
    "price",
    "school",
    "telegram",
    "until",
    "with",
}


st.set_page_config(
    page_title="Medsight Pipeline Demo",
    page_icon="M",
    layout="wide",
)


@st.cache_data(show_spinner=False)
def load_messages() -> pd.DataFrame:
    records = []
    for json_file in sorted(MESSAGES_DIR.rglob("*.json")):
        with json_file.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list):
            records.extend(data)

    if not records:
        return pd.DataFrame(
            columns=[
                "message_id",
                "channel_name",
                "message_date",
                "message_text",
                "has_media",
                "image_path",
                "views",
                "forwards",
            ]
        )

    df = pd.DataFrame(records)
    df["message_date"] = pd.to_datetime(df["message_date"], errors="coerce", utc=True)
    df["date"] = df["message_date"].dt.date
    df["message_text"] = df["message_text"].fillna("")
    df["views"] = pd.to_numeric(df["views"], errors="coerce").fillna(0).astype(int)
    df["forwards"] = pd.to_numeric(df["forwards"], errors="coerce").fillna(0).astype(int)
    df["has_media"] = df["has_media"].fillna(False).astype(bool)
    df["price_birr"] = df["message_text"].apply(extract_price)
    df["product_name"] = df["message_text"].apply(extract_product_name)
    return df


@st.cache_data(show_spinner=False)
def load_yolo() -> pd.DataFrame:
    if not YOLO_CSV.exists():
        return pd.DataFrame(
            columns=[
                "message_id",
                "channel_name",
                "image_path",
                "detected_objects_count",
                "top_detected_class",
                "top_confidence",
                "image_category",
            ]
        )

    df = pd.read_csv(YOLO_CSV)
    df["message_id"] = pd.to_numeric(df["message_id"], errors="coerce")
    df["detected_objects_count"] = pd.to_numeric(
        df["detected_objects_count"], errors="coerce"
    ).fillna(0)
    df["top_confidence"] = pd.to_numeric(df["top_confidence"], errors="coerce").fillna(0)
    return df


def extract_price(text: str) -> float | None:
    match = re.search(r"price\s*[:\-]?\s*([0-9][0-9,]*)", text, flags=re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def extract_product_name(text: str) -> str:
    for raw_line in text.splitlines():
        line = re.sub(r"[*_`~]+", "", raw_line).strip()
        if not line:
            continue
        if re.search(r"price|telegram|msg|call|address|adress|open|delivery", line, re.I):
            continue
        return re.sub(r"\s+", " ", line)[:80]
    return "Unlabeled product"


def top_terms(texts: pd.Series, limit: int = 15) -> pd.DataFrame:
    words = []
    for text in texts:
        words.extend(
            word.lower()
            for word in re.findall(r"[A-Za-z][A-Za-z0-9+]{2,}", text)
            if word.lower() not in STOP_WORDS
        )
    counts = Counter(words).most_common(limit)
    return pd.DataFrame(counts, columns=["term", "mentions"])


def metric_row(df: pd.DataFrame, yolo: pd.DataFrame) -> None:
    total_views = int(df["views"].sum()) if not df.empty else 0
    media_rate = (df["has_media"].mean() * 100) if not df.empty else 0
    avg_price = df["price_birr"].dropna().mean() if not df.empty else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Messages", f"{len(df):,}")
    col2.metric("Images analyzed", f"{len(yolo):,}")
    col3.metric("Total views", f"{total_views:,}")
    col4.metric("Avg. listed price", f"{avg_price:,.0f} birr")

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Channels", f"{df['channel_name'].nunique() if not df.empty else 0:,}")
    col6.metric("Media share", f"{media_rate:.1f}%")
    col7.metric(
        "Detected objects",
        f"{int(yolo['detected_objects_count'].sum()) if not yolo.empty else 0:,}",
    )
    col8.metric(
        "Avg. YOLO confidence",
        f"{yolo['top_confidence'].mean():.2f}" if not yolo.empty else "0.00",
    )


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    st.sidebar.header("Filters")
    channels = sorted(df["channel_name"].dropna().unique())
    selected_channels = st.sidebar.multiselect("Channels", channels, default=channels)

    min_date = df["date"].min()
    max_date = df["date"].max()
    selected_dates = st.sidebar.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    query = st.sidebar.text_input("Search messages", "")
    min_views = st.sidebar.slider(
        "Minimum views",
        0,
        int(df["views"].max()) if not df.empty else 0,
        0,
    )

    filtered = df[df["channel_name"].isin(selected_channels)]
    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        start_date, end_date = selected_dates
        filtered = filtered[(filtered["date"] >= start_date) & (filtered["date"] <= end_date)]

    filtered = filtered[filtered["views"] >= min_views]
    if query:
        filtered = filtered[
            filtered["message_text"].str.contains(query, case=False, na=False)
            | filtered["product_name"].str.contains(query, case=False, na=False)
        ]
    return filtered


def overview_tab(df: pd.DataFrame, yolo: pd.DataFrame) -> None:
    left, right = st.columns([1.25, 1])

    with left:
        st.subheader("Daily posting activity")
        daily = df.groupby("date", as_index=False).agg(
            messages=("message_id", "count"),
            views=("views", "sum"),
        )
        st.line_chart(daily.set_index("date")[["messages", "views"]])

    with right:
        st.subheader("Visual categories")
        if yolo.empty:
            st.info("No YOLO detection file found.")
        else:
            category_counts = yolo["image_category"].value_counts().rename_axis("category")
            st.bar_chart(category_counts)

    st.subheader("Channel summary")
    channel_summary = (
        df.groupby("channel_name", as_index=False)
        .agg(
            messages=("message_id", "count"),
            total_views=("views", "sum"),
            avg_views=("views", "mean"),
            media_posts=("has_media", "sum"),
        )
        .sort_values("messages", ascending=False)
    )
    st.dataframe(channel_summary, use_container_width=True, hide_index=True)


def products_tab(df: pd.DataFrame) -> None:
    left, right = st.columns([1, 1])

    with left:
        st.subheader("Most mentioned terms")
        terms = top_terms(df["message_text"])
        if terms.empty:
            st.info("No terms found for the current filter.")
        else:
            st.bar_chart(terms.set_index("term"))

    with right:
        st.subheader("Price distribution")
        prices = df["price_birr"].dropna()
        if prices.empty:
            st.info("No prices found in the current filter.")
        else:
            buckets = pd.cut(prices, bins=8).value_counts().sort_index()
            buckets.index = buckets.index.astype(str)
            st.bar_chart(buckets)

    st.subheader("Top product-style listings")
    product_table = (
        df[df["product_name"] != "Unlabeled product"]
        .sort_values("views", ascending=False)[
            ["product_name", "channel_name", "price_birr", "views", "forwards", "message_date"]
        ]
        .head(40)
    )
    st.dataframe(product_table, use_container_width=True, hide_index=True)


def messages_tab(df: pd.DataFrame) -> None:
    st.subheader("Searchable message sample")
    display = df.sort_values("message_date", ascending=False)[
        [
            "message_id",
            "channel_name",
            "product_name",
            "price_birr",
            "views",
            "forwards",
            "message_date",
            "message_text",
        ]
    ].head(100)
    st.dataframe(display, use_container_width=True, hide_index=True)


def visual_tab(df: pd.DataFrame, yolo: pd.DataFrame) -> None:
    if yolo.empty:
        st.info("No YOLO detection file found.")
        return

    enriched = yolo.merge(
        df[["message_id", "channel_name", "product_name", "views", "message_text"]],
        on=["message_id", "channel_name"],
        how="left",
    )

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Top detected classes")
        classes = (
            enriched["top_detected_class"]
            .dropna()
            .replace("", pd.NA)
            .dropna()
            .value_counts()
            .head(15)
        )
        st.bar_chart(classes)

    with col2:
        st.subheader("Average views by image category")
        category_views = (
            enriched.groupby("image_category")["views"].mean().sort_values(ascending=False)
        )
        st.bar_chart(category_views)

    st.subheader("YOLO detection results")
    st.dataframe(
        enriched[
            [
                "message_id",
                "channel_name",
                "product_name",
                "image_category",
                "top_detected_class",
                "top_confidence",
                "detected_objects_count",
                "views",
            ]
        ].sort_values("top_confidence", ascending=False),
        use_container_width=True,
        hide_index=True,
    )


def gallery_tab(df: pd.DataFrame, yolo: pd.DataFrame) -> None:
    if yolo.empty:
        st.info("No images are available for the gallery.")
        return

    categories = ["All"] + sorted(yolo["image_category"].dropna().unique().tolist())
    selected_category = st.selectbox("Image category", categories)
    gallery = yolo.copy()
    if selected_category != "All":
        gallery = gallery[gallery["image_category"] == selected_category]

    gallery = gallery.merge(
        df[["message_id", "channel_name", "product_name", "views"]],
        on=["message_id", "channel_name"],
        how="left",
    ).sort_values(["top_confidence", "views"], ascending=False)

    limit = st.slider("Gallery size", 6, 48, 12, step=6)
    cols = st.columns(3)
    shown = 0
    for idx, row in gallery.head(limit).iterrows():
        image_path = BASE_DIR / str(row["image_path"])
        if not image_path.exists():
            continue
        with cols[shown % 3]:
            st.image(str(image_path), use_container_width=True)
            st.caption(
                f"{row.get('product_name', 'Unlabeled product')} | "
                f"{row.get('image_category', 'other')} | "
                f"{row.get('top_detected_class', 'no class')}"
            )
        shown += 1

    if shown == 0:
        st.info(f"No image files found under {IMAGE_DIR}.")


def main() -> None:
    st.title("Medsight Pipeline Demo")
    st.caption("Telegram marketplace messages, YOLO image enrichment, and analytics demo")

    messages = load_messages()
    yolo = load_yolo()

    if messages.empty:
        st.error("No local Telegram message data found under data/raw/telegram_messages.")
        return

    filtered = apply_filters(messages)
    filtered_yolo = yolo.merge(
        filtered[["message_id", "channel_name"]],
        on=["message_id", "channel_name"],
        how="inner",
    )

    metric_row(filtered, filtered_yolo)

    overview, products, messages_tab_item, visual, gallery = st.tabs(
        ["Overview", "Products", "Messages", "Visual AI", "Gallery"]
    )

    with overview:
        overview_tab(filtered, filtered_yolo)
    with products:
        products_tab(filtered)
    with messages_tab_item:
        messages_tab(filtered)
    with visual:
        visual_tab(filtered, filtered_yolo)
    with gallery:
        gallery_tab(filtered, filtered_yolo)


if __name__ == "__main__":
    main()

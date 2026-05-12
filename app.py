import streamlit as st
import polars as pl
import json
import os
import re

# Set page config
st.set_page_config(page_title="The Census Archive", layout="wide")

# Updated Table Series mapping
SERIES_TITLES = {
    "A": "General Population Tables",
    "B": "General Economic Tables",
    "C": "Social and Cultural Tables",
    "D": "Migration Tables",
    "F": "Fertility Tables",
    "H": "Housing Tables",
    "HH": "Household Tables",
    "PCA": "Primary Census Abstract",
    "SC": "Scheduled Castes Tables",
    "ST": "Scheduled Tribes Tables",
    "DIS": "Disability Tables",
    "FH": "Female-headed Households Tables",
    "HL": "Household Amenities Tables",
    "Other": "Other / Miscellaneous"
}

@st.cache_data
def load_data():
    df = pl.read_parquet("Data/processed_census_full.parquet").fill_null("")
    df = df.with_columns(pl.col("downloads").cast(pl.Int64))
    with open("Data/census_app_metadata.json", 'r') as f:
        meta = json.load(f)
    return df, meta

def reset_filters():
    for key in st.session_state.keys():
        if key.startswith("filter_") or key == "free_search_input":
            if isinstance(st.session_state[key], list):
                st.session_state[key] = []
            else:
                st.session_state[key] = ""

def main():
    # Elegant serif font for header (New Yorker style)
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;1,700&display=swap');

        .main-header {
            font-family: 'Playfair Display', serif;
            font-size: 4rem;
            font-weight: 700;
            color: inherit;
            text-align: center;
            margin-bottom: 0.2rem;
            letter-spacing: -2px;
            text-transform: uppercase;
        }
        .sub-header {
            font-family: 'Playfair Display', serif;
            font-style: italic;
            font-size: 1.2rem;
            color: inherit;
            opacity: 0.8;
            text-align: center;
            margin-bottom: 2rem;
            border-bottom: 2px solid;
            padding-bottom: 1rem;
            max-width: 800px;
            margin-left: auto;
            margin-right: auto;
        }
        .footer {
            font-family: 'Georgia', serif;
            font-size: 0.85rem;
            text-align: center;
            margin-top: 4rem;
            padding: 2rem 0;
            border-top: 1px solid rgba(128, 128, 128, 0.2);
            color: inherit;
            opacity: 0.7;
            letter-spacing: 1px;
            text-transform: uppercase;
        }
        /* Sidebar styling */
        .stMultiSelect label, .stSelectbox label, .stTextInput label {
            font-family: 'Georgia', serif !important;
            font-weight: bold !important;
            text-transform: uppercase;
            font-size: 0.8rem !important;
            letter-spacing: 1px;
        }
        </style>
        <div class="main-header">The Census Archive</div>
        <div class="sub-header">A complete digital repository of the Indian Census Catalog</div>
    """, unsafe_allow_html=True)

    if not os.path.exists("Data/processed_census_full.parquet"):
        st.error("Processed data not found. Please run the processing script first.")
        return

    df, meta = load_data()

    # Sidebar Filters
    st.sidebar.header("CATALOG FILTERS")
    if st.sidebar.button("RESET ALL"):
        reset_filters()
        st.rerun()

    # 1. Select Table Series
    all_series = sorted(df["table_series"].unique().to_list())
    if "" in all_series: all_series.remove("")
    series_options = [f"{s} - {SERIES_TITLES.get(s, 'Unknown Series')}" for s in all_series]
    selected_series_labels = st.sidebar.multiselect("SERIES", series_options, key="filter_series")
    selected_series = [s.split(" - ")[0] for s in selected_series_labels]

    # 2. Select Sub-Table
    if selected_series:
        available_tables = sorted(df.filter(pl.col("table_series").is_in(selected_series))["table_type"].unique().to_list())
    else:
        available_tables = sorted(df["table_type"].unique().to_list())
    if "" in available_tables: available_tables.remove("")
    selected_tables = st.sidebar.multiselect("SUB-TABLES", available_tables, key="filter_tables")

    # 3. State Filter
    all_states = sorted(df["state"].unique().to_list())
    if "" in all_states: all_states.remove("")
    selected_states = st.sidebar.multiselect("STATES / UT", all_states, key="filter_states")

    # 4. Census Year Filter
    priority_years = ["2011", "2001", "1991", "1981", "1971", "1961", "1951"]
    all_years_found = sorted(df["census_year"].unique().to_list())
    year_options = [y for y in priority_years if y in all_years_found]
    if "Other" in all_years_found: year_options.append("Other")
    if "Unknown" in all_years_found: year_options.append("Unknown")
    selected_years = st.sidebar.multiselect("CENSUS YEARS", year_options, key="filter_years")

    # 5. Sub-Filters
    raw_filters_list = df["filters"].unique().to_list()
    unique_filters = set()
    for f_str in raw_filters_list:
        if f_str:
            for f in f_str.split(", "): unique_filters.add(f)
    selected_sub_filters = st.sidebar.multiselect("KEYWORDS", sorted(list(unique_filters)), key="filter_sub")

    # 6. Tags
    selected_tags_1 = st.sidebar.multiselect("TOPICS (1-word)", meta["top_30_1word"], key="filter_tags1")
    selected_tags_2 = st.sidebar.multiselect("TOPICS (2-word)", meta["top_30_2word"], key="filter_tags2")

    # Free Search
    free_search = st.text_input("FREE TEXT SEARCH", placeholder="e.g. Migration Bihar", key="free_search_input")

    # --- Apply Filtering ---
    filtered_df = df
    if selected_series: filtered_df = filtered_df.filter(pl.col("table_series").is_in(selected_series))
    if selected_tables: filtered_df = filtered_df.filter(pl.col("table_type").is_in(selected_tables))
    if selected_states: filtered_df = filtered_df.filter(pl.col("state").is_in(selected_states))
    if selected_years: filtered_df = filtered_df.filter(pl.col("census_year").is_in(selected_years))
    if selected_sub_filters:
        filter_query = pl.lit(False)
        for f in selected_sub_filters: filter_query = filter_query | pl.col("filters").str.contains(re.escape(f))
        filtered_df = filtered_df.filter(filter_query)

    # SMART TAG FILTERING
    if selected_tags_1:
        for tag in selected_tags_1:
            filtered_df = filtered_df.filter(pl.col("title").str.to_lowercase().str.contains(re.escape(tag.lower())))
    if selected_tags_2:
        for tag in selected_tags_2:
            words = tag.lower().split()
            for word in words:
                filtered_df = filtered_df.filter(pl.col("title").str.to_lowercase().str.contains(re.escape(word)))

    if free_search:
        search_terms = free_search.lower().split()
        for term in search_terms: filtered_df = filtered_df.filter(pl.col("title").str.to_lowercase().str.contains(re.escape(term)))

    # --- Sorting & Display ---
    filtered_df = filtered_df.sort("downloads", descending=True)
    display_limit = 1000
    total_results = filtered_df.height
    st.write(f"Displaying {min(total_results, display_limit)} of {total_results} archive entries (Ranked by popularity)")

    if total_results > 0:
        display_df = filtered_df.head(display_limit).select([
            pl.col("title").alias("Title"),
            pl.col("state").alias("State"),
            pl.col("census_year").alias("Year"),
            pl.col("table_type").alias("Table"),
            pl.col("filters").alias("Filter"),
            pl.col("downloads").alias("Downloads"),
            pl.col("link").alias("Catalog"),
            pl.col("direct_link").alias("File")
        ]).to_pandas()

        st.dataframe(
            display_df,
            column_config={
                "Title": st.column_config.TextColumn("Title", width=800),
                "Catalog": st.column_config.LinkColumn("Catalog", display_text="Page", width="small"),
                "File": st.column_config.LinkColumn("File", display_text="Download", width="small"),
                "Downloads": st.column_config.NumberColumn("Downloads", format="%d")
            },
            hide_index=True,
            use_container_width=True
        )

        st.caption("Double-click a Title cell to see the full text. Click any header to sort the collection.")
    else:
        st.write("No entries found matching your search criteria.")

    # Professional Footer
    st.markdown("""
        <div class="footer">
            Developed by Jonathan Old
        </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()

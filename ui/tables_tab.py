"""
ui/tables_tab.py

Streamlit UI component for the Tables tab.
"""
import streamlit as st
import pandas as pd
import math

from services.table_service import get_table_metadata
from utils.downloads import dataframe_to_csv_bytes, dataframe_to_excel_bytes, dataframe_to_json_bytes

@st.cache_data(show_spinner=False)
def get_cached_table_metadata(_doc):
    return get_table_metadata(_doc)

def render_tables_tab(doc):
    if not doc:
        st.warning("No document loaded.")
        return
        
    with st.spinner("Extracting table metadata..."):
        tables_meta = get_cached_table_metadata(doc)
        
    if not tables_meta:
        st.info("No tables found in this document.")
        return
        
    # Compute Metrics
    total_tables = len(tables_meta)
    referenced = sum(1 for m in tables_meta if m["is_referenced"])
    downloadable = sum(1 for m in tables_meta if not m["dataframe"].empty)
    
    st.markdown("### Tables Overview")
    c1, c2, c3 = st.columns(3)
    c1.metric("Tables Found", total_tables)
    c2.metric("Referenced", referenced)
    c3.metric("Downloadable", downloadable)
    
    st.divider()
    
    # Sidebar Filters
    with st.sidebar:
        st.subheader("📊 Table Filters")
        
        filter_status = st.selectbox(
            "Reference Status (Tables)",
            ["All", "Referenced", "Unreferenced"]
        )
        
        filter_size = st.selectbox(
            "Table Size",
            ["All", "Large Tables (>10 rows)", "Small Tables (<=10 rows)"]
        )
        
    # Search Bar
    search_query = st.text_input("🔍 Search Tables (Caption, Title, Keywords)")
    
    # Apply Filters & Search
    filtered_tables = tables_meta
    
    if filter_status == "Referenced":
        filtered_tables = [t for t in filtered_tables if t["is_referenced"]]
    elif filter_status == "Unreferenced":
        filtered_tables = [t for t in filtered_tables if not t["is_referenced"]]
        
    if filter_size == "Large Tables (>10 rows)":
        filtered_tables = [t for t in filtered_tables if t["rows"] > 10]
    elif filter_size == "Small Tables (<=10 rows)":
        filtered_tables = [t for t in filtered_tables if t["rows"] <= 10]
        
    if search_query:
        sq = search_query.lower()
        filtered_tables = [
            t for t in filtered_tables
            if sq in str(t.get("caption", "")).lower() or 
               sq in str(t.get("table_number", "")).lower()
        ]
        
    if not filtered_tables:
        st.info("No tables match your filters/search.")
        return
        
    st.markdown(f"**Showing {len(filtered_tables)} tables**")
    
    for i, tbl in enumerate(filtered_tables):
        with st.container(border=True):
            tbl_num = tbl.get("table_number") or "Unknown"
            caption = tbl.get("caption") or "No caption found"
            
            st.markdown(f"#### Table {tbl_num}")
            st.caption(caption)
            
            c_meta1, c_meta2, c_meta3 = st.columns(3)
            c_meta1.write(f"**Page:** {tbl['page']}")
            c_meta2.write(f"**Dimensions:** {tbl['rows']} rows x {tbl['columns']} cols")
            ref_icon = "✅" if tbl["is_referenced"] else "❌"
            c_meta3.write(f"**Referenced:** {ref_icon}")
            
            df = tbl["dataframe"]
            if df.empty:
                st.warning("Table could not be reconstructed as a dataframe.")
            else:
                st.dataframe(df, width="stretch", hide_index=True)
                
                # Download buttons
                dl_cols = st.columns([1, 1, 1, 3])
                
                csv_bytes = dataframe_to_csv_bytes(df)
                dl_cols[0].download_button(
                    label="CSV",
                    data=csv_bytes,
                    file_name=f"table_{tbl_num}_p{tbl['page']}.csv",
                    mime="text/csv",
                    key=f"csv_{tbl['id']}",
                    width="stretch"
                )
                
                try:
                    excel_bytes = dataframe_to_excel_bytes(df)
                    dl_cols[1].download_button(
                        label="Excel",
                        data=excel_bytes,
                        file_name=f"table_{tbl_num}_p{tbl['page']}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"xlsx_{tbl['id']}",
                        width="stretch"
                    )
                except Exception as e:
                    dl_cols[1].error("Excel err")
                    
                json_bytes = dataframe_to_json_bytes(df)
                dl_cols[2].download_button(
                    label="JSON",
                    data=json_bytes,
                    file_name=f"table_{tbl_num}_p{tbl['page']}.json",
                    mime="application/json",
                    key=f"json_{tbl['id']}",
                    width="stretch"
                )

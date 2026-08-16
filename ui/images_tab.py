"""
ui/images_tab.py

Streamlit UI component for the Images tab.
"""
import streamlit as st
import pandas as pd
import math

from services.image_service import get_image_metadata, extract_image_bytes, generate_thumbnail

@st.cache_data(show_spinner=False)
def get_cached_metadata(_doc):
    return get_image_metadata(_doc)

@st.cache_data(show_spinner=False, max_entries=200)
def get_cached_thumbnail(pdf_bytes: bytes, page_num: int, xref: int, bbox: tuple):
    img_bytes = extract_image_bytes(pdf_bytes, page_num, xref, bbox)
    return generate_thumbnail(img_bytes)

def render_images_tab(doc, pdf_bytes: bytes):
    if not doc or not pdf_bytes:
        st.warning("No document loaded.")
        return
        
    # Get Metadata
    with st.spinner("Extracting image metadata..."):
        images_meta = get_cached_metadata(doc)
        
    if not images_meta:
        st.info("No images found in this document.")
        return
        
    # Compute Metrics
    total_images = len(images_meta)
    referenced = sum(1 for m in images_meta if m["is_referenced"])
    unreferenced = total_images - referenced
    low_res = sum(1 for m in images_meta if m["dpi_x"] > 0 and (m["dpi_x"] < 300 or m["dpi_y"] < 300))
    
    st.markdown("### Images Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Images Found", total_images)
    c2.metric("Referenced", referenced)
    c3.metric("Unreferenced", unreferenced)
    c4.metric("Low Resolution", low_res, help="Images with < 300 DPI")
    
    st.divider()
    
    # Sidebar Filters
    with st.sidebar:
        st.subheader("🖼️ Image Filters")
        
        filter_status = st.selectbox(
            "Reference Status",
            ["All", "Referenced", "Unreferenced"]
        )
        
        filter_res = st.selectbox(
            "Resolution",
            ["All", "High Resolution (≥300)", "Low Resolution (<300)"]
        )
        
        sort_by = st.selectbox(
            "Sort by",
            ["Page", "Caption", "DPI (High to Low)", "DPI (Low to High)"]
        )
        
    # Search Bar
    search_query = st.text_input("🔍 Search Images (Caption, Figure Number, or Keywords)")
    
    # Apply Filters & Search
    filtered_images = images_meta
    
    if filter_status == "Referenced":
        filtered_images = [img for img in filtered_images if img["is_referenced"]]
    elif filter_status == "Unreferenced":
        filtered_images = [img for img in filtered_images if not img["is_referenced"]]
        
    if filter_res == "High Resolution (≥300)":
        filtered_images = [img for img in filtered_images if img["dpi_x"] >= 300]
    elif filter_res == "Low Resolution (<300)":
        filtered_images = [img for img in filtered_images if 0 < img["dpi_x"] < 300]
        
    if search_query:
        sq = search_query.lower()
        filtered_images = [
            img for img in filtered_images
            if sq in str(img.get("caption", "")).lower() or 
               sq in str(img.get("figure_number", "")).lower() or
               sq == str(img["page"])
        ]
        
    # Apply Sort
    if sort_by == "Page":
        filtered_images.sort(key=lambda x: x["page"])
    elif sort_by == "Caption":
        filtered_images.sort(key=lambda x: str(x.get("caption", "")))
    elif sort_by == "DPI (High to Low)":
        filtered_images.sort(key=lambda x: x["dpi_x"], reverse=True)
    elif sort_by == "DPI (Low to High)":
        filtered_images.sort(key=lambda x: x["dpi_x"])
        
    if not filtered_images:
        st.info("No images match your filters/search.")
        return
        
    # Gallery Grid
    st.markdown(f"**Showing {len(filtered_images)} images**")
    
    # Pagination
    items_per_page = 12
    total_pages = math.ceil(len(filtered_images) / items_per_page)
    
    page_num = 1
    if total_pages > 1:
        page_num = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
        
    start_idx = (page_num - 1) * items_per_page
    end_idx = start_idx + items_per_page
    current_items = filtered_images[start_idx:end_idx]
    
    # Layout 3 columns
    cols = st.columns(3)
    
    for i, img in enumerate(current_items):
        col = cols[i % 3]
        with col:
            with st.container(border=True):
                # Thumbnail
                thumb = get_cached_thumbnail(pdf_bytes, img["page"], img["xref"], img["bbox"])
                if thumb:
                    st.image(thumb, width="stretch")
                else:
                    st.warning("Thumbnail unavailable")
                    
                # Details
                fig_num = img.get("figure_number") or "Unknown"
                st.markdown(f"**Figure {fig_num}**")
                
                caption = img.get("caption") or "No caption found"
                if len(caption) > 60:
                    caption = caption[:57] + "..."
                st.caption(caption)
                
                st.markdown(f"**Page:** {img['page']}")
                st.markdown(f"**Resolution:** {img['width']} × {img['height']}")
                st.markdown(f"**DPI:** {img['dpi_x']}")
                
                ref_icon = "✅" if img["is_referenced"] else "❌"
                st.markdown(f"**Referenced:** {ref_icon}")
                
                # Actions
                btn_cols = st.columns(2)
                with btn_cols[0]:
                    if st.button("View Details", key=f"details_{img['id']}", width="stretch"):
                        _show_image_dialog(img, pdf_bytes)
                with btn_cols[1]:
                    img_data = extract_image_bytes(pdf_bytes, img["page"], img["xref"], img["bbox"])
                    if img_data:
                        st.download_button(
                            label="Download",
                            data=img_data,
                            file_name=f"figure_{fig_num}_page_{img['page']}.png",
                            mime="image/png",
                            key=f"dl_{img['id']}",
                            width="stretch"
                        )

@st.dialog("Image Details")
def _show_image_dialog(img_meta: dict, pdf_bytes: bytes):
    st.markdown(f"### Figure {img_meta.get('figure_number', 'Unknown')}")
    st.markdown(f"**Caption:** {img_meta.get('caption', 'None')}")
    
    img_data = extract_image_bytes(pdf_bytes, img_meta["page"], img_meta["xref"], img_meta["bbox"])
    if img_data:
        st.image(img_data, width="stretch")
        
    st.markdown("#### Metadata")
    c1, c2 = st.columns(2)
    c1.write(f"**Page:** {img_meta['page']}")
    c1.write(f"**Dimensions:** {img_meta['width']} x {img_meta['height']} px")
    c2.write(f"**DPI:** {img_meta['dpi_x']} x {img_meta['dpi_y']}")
    c2.write(f"**Colorspace:** {img_meta['colorspace']}")
    
    st.markdown("#### References")
    if img_meta["is_referenced"]:
        st.write(f"Referenced on pages: {', '.join(map(str, img_meta['referenced_pages']))}")
    else:
        st.warning("This figure is not referenced in the document text.")

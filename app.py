#!/usr/bin/env python3
"""
智能票据识别助手 - Web 应用
基于 Streamlit + PaddleOCR，支持上传 PDF/图片，自动 OCR 识别，票据信息提取，导出 TXT。

使用方法：
  1. pip install streamlit paddlepaddle paddleocr PyMuPDF
  2. streamlit run app.py
  3. 浏览器自动打开
"""

import os
import re
import tempfile
import datetime

import streamlit as st
import fitz  # PyMuPDF
from paddleocr import PaddleOCR

# ============================================================
# 全局初始化
# ============================================================

@st.cache_resource
def get_ocr_engine():
    return PaddleOCR(use_angle_cls=True, lang="ch")


# ============================================================
# PDF 转图片
# ============================================================


def pdf_to_images(pdf_path):
    doc = fitz.open(pdf_path)
    paths = []
    for i, page in enumerate(doc):
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)
        path = os.path.join(tempfile.gettempdir(), f"ocr_page_{i}.png")
        pix.save(path)
        paths.append(path)
    doc.close()
    return paths


# ============================================================
# OCR 识别
# ============================================================


def ocr_image(image_path):
    engine = get_ocr_engine()
    result = engine.ocr(image_path)
    lines = []
    if result and result[0]:
        for line in result[0]:
            lines.append(line[1][0])
    return "\n".join(lines)


def ocr_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        image_paths = pdf_to_images(file_path)
    else:
        image_paths = [file_path]

    all_text = []
    for idx, img_path in enumerate(image_paths):
        text = ocr_image(img_path)
        if len(image_paths) > 1:
            all_text.append(f"--- 第 {idx + 1} 页 ---\n{text}")
        else:
            all_text.append(text)

    return "\n\n".join(all_text), len(image_paths)


# ============================================================
# 票据信息提取
# ============================================================


def extract_bill_info(text):
    info = {}

    date_patterns = [
        r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\s*\d{0,2}:\d{0,2})",
        r"(\d{4}年\d{1,2}月\d{1,2}日\s*\d{0,2}:\d{0,2})",
        r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})",
        r"(\d{4}年\d{1,2}月\d{1,2}日)",
    ]
    for pat in date_patterns:
        m = re.search(pat, text)
        if m:
            info["日期"] = m.group(1)
            break
    else:
        info["日期"] = "识别失败"

    amount_patterns = [
        r"(?:总[额计]|合[计计]|金额|价税合计|应收|实付|实收|总计)[：:\s]*[¥￥]?\s*([\d,]+\.?\d*)",
        r"[¥￥]\s*([\d,]+\.?\d*)",
        r"(?:金额|合计|总计)[：:\s]*([\d,]+\.?\d*)",
    ]
    for pat in amount_patterns:
        m = re.search(pat, text)
        if m:
            info["总额"] = m.group(1)
            break
    else:
        info["总额"] = "识别失败"

    merchant_patterns = [
        r"(?:商户|销售方|收款方|开票方|卖方|供应商|商家)[名称：:\s]*([^\n,，]{2,30})",
        r"(?:名称)[：:\s]*([^\n,，]{2,30})",
    ]
    for pat in merchant_patterns:
        m = re.search(pat, text)
        if m:
            info["商户名称"] = m.group(1).strip()
            break
    else:
        company_m = re.search(r"([\u4e00-\u9fa5]+(?:公司|店|铺|商行|部))", text)
        info["商户名称"] = company_m.group(1) if company_m else "识别失败"

    detail_patterns = [
        r"(?:商品|项目|明细|品名|货物|服务)[名称：:\s]*([^\n]+)",
        r"(?:项目|品名)[：:\s]*(.+?)(?:\n|$)",
    ]
    details = []
    for pat in detail_patterns:
        for m in re.finditer(pat, text):
            d = m.group(1).strip()
            if d and d not in details:
                details.append(d)

    if details:
        info["商品明细"] = "\n    ".join(details)
    else:
        non_empty = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 1]
        if non_empty:
            info["商品明细"] = "\n    ".join(non_empty[:10]) + ("\n    ..." if len(non_empty) > 10 else "")
        else:
            info["商品明细"] = "识别失败"

    return info


# ============================================================
# Streamlit 界面
# ============================================================

st.set_page_config(page_title="智能票据识别助手", page_icon="🔍", layout="wide")

st.title("🔍 智能票据识别助手")
st.caption("上传 PDF 或图片，自动识别文字，提取票据关键信息，支持导出 TXT")

col1, col2 = st.columns([1, 2])

with col1:
    uploaded_file = st.file_uploader(
        "📤 上传文件",
        type=["pdf", "jpg", "jpeg", "png", "bmp", "tiff", "tif", "webp"],
    )
    mode = st.radio("🛠 识别模式", ["票据信息提取", "通用文字识别"],
                     index=0, help="票据模式自动提取日期/金额/商户等字段")

    run_btn = st.button("🚀 开始识别", type="primary", use_container_width=True)

with col2:
    result_area = st.empty()

if run_btn and uploaded_file is not None:
    with st.spinner("正在识别中，请稍候..."):
        try:
            suffix = os.path.splitext(uploaded_file.name)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded_file.getbuffer())
                tmp_path = tmp.name

            raw_text, num_pages = ocr_file(tmp_path)
            filename = uploaded_file.name

            if not raw_text.strip():
                result_area.error("识别失败：未提取到任何文字内容")
            else:
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                header = f"文件：{filename}  |  识别时间：{now}  |  页数：{num_pages}"

                if mode == "票据信息提取":
                    info = extract_bill_info(raw_text)
                    result_text = (
                        f"=== OCR 识别结果 ===\n{header}\n\n"
                        f"=== 票据信息提取 ===\n\n"
                        f"【日期】{info.get('日期', '识别失败')}\n"
                        f"【总额】{info.get('总额', '识别失败')}\n"
                        f"【商户名称】{info.get('商户名称', '识别失败')}\n"
                        f"【商品明细】\n    {info.get('商品明细', '识别失败')}\n\n"
                        f"=== 原文 ===\n{raw_text}"
                    )
                else:
                    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
                    cleaned = "\n".join(lines)
                    result_text = (
                        f"=== OCR 识别结果 ===\n{header}\n\n"
                        f"=== 文本内容 ===\n{cleaned}"
                    )

                result_area.code(result_text, language=None)

                st.download_button(
                    "📥 下载 TXT 文件",
                    data=result_text.encode("utf-8"),
                    file_name=f"{os.path.splitext(filename)[0]}_OCR结果.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

            os.unlink(tmp_path)

        except Exception as e:
            result_area.error(f"处理出错：{str(e)}")

elif run_btn and uploaded_file is None:
    st.warning("请先上传文件")
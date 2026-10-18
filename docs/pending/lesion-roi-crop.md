# [Pending] Xác định vùng tổn thương (ROI) trước khi phân loại bằng CNN

Chưa làm, không phải cam kết. Ý tưởng: tiền xử lý ảnh bằng **kỹ thuật phân đoạn cổ điển** hoặc **model có sẵn
trên Hugging Face** để cắt vùng tổn thương, rồi đưa vùng đó cho CNN `classify_skin_image`
(`core/agent/tools/skin_image_classifier.py`).

## 1. Vấn đề

CNN (22 lớp, ảnh 224x224) nhận nguyên ảnh người dùng gửi. Khi ảnh chụp xa, nhiều nền (quần áo, phòng) hoặc tổn
thương nhỏ, phần tổn thương chỉ chiếm một góc nên xác suất phân loại kém tin cậy.

## 2. Luồng đề xuất

```
ảnh gốc ─▶ phân đoạn (cổ điển / HF) ─▶ bbox ─▶ crop (+ lề ~15%) ─┬▶ CNN(crop)
                                                                 └▶ CNN(ảnh gốc) ─▶ so top-1, báo bất định nếu khác
```

- Là bước tiền xử lý **nội bộ** (hàm dùng chung), không phải tool cho LLM gọi, để khỏi tốn ngân sách tool và
  khỏi để LLM chép lại `object_key`.
- Luôn fallback ảnh gốc khi không tìm được vùng, box quá nhỏ, hoặc phủ >70% ảnh.

## 3. Cách xác định vùng

| Cách | Ưu | Nhược |
|---|---|---|
| Phân đoạn cổ điển (ngưỡng trên không gian Lab, GrabCut) | Rẻ, không thêm dependency model, dễ giải thích | Kém khi nền phức tạp, ánh sáng xấu |
| Model phân đoạn trên Hugging Face: `mahnoor-2722/isic-segformer` (SegFormer MiT-B0), `NajmiHassan1/SkinSeg-Vision` (U-Net ResNet-34) | Có mask thật, chạy CPU được | Huấn luyện trên ISIC (dermoscopy, một nốt sắc tố), lệch miền so với ảnh lâm sàng 22 lớp; số liệu do tác giả tự báo, chưa kiểm chứng độc lập |

Model detection YOLO trên Hugging Face hiện chỉ phủ vài loại (mụn, nốt ruồi, rosacea), chất lượng thấp, không đủ
cho 22 lớp.

## 4. Câu hỏi cần chốt

- Crop có thật sự cải thiện top-1 CNN so với ảnh gốc? Cần đo trên 20–50 ảnh có nhãn thật trước khi đặt crop làm
  kết quả chính.
- Bệnh lan toả (eczema, mề đay, tinea, mụn) không có "một vùng": có bỏ qua ROI cho nhóm này không?
- Nhiều tổn thương trong một ảnh thì crop vùng nào (lớn nhất, hay chạy CNN từng vùng)?
- CNN được huấn luyện trên ảnh cận cảnh hay nguyên khung? Nếu nguyên khung thì crop có thể làm lệch phân phối.

## 5. Phụ thuộc

- Bộ ảnh mẫu có nhãn để đo (xem `core/agent/test/`).
- Nếu dùng model Hugging Face: thêm `transformers` (hoặc `segmentation-models-pytorch`) cho Agent Worker.

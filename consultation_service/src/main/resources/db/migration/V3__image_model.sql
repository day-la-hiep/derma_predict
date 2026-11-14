-- Thêm lựa chọn model CNN phân loại ảnh theo từng hội thoại (id mềm, không FK).
-- Mặc định EfficientNet-B0 (nhẹ, 70% val acc) để máy yếu vẫn chạy được.
ALTER TABLE conversations ADD COLUMN image_model VARCHAR(64) NOT NULL DEFAULT 'efficientnet-b0';
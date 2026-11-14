package vn.derma.clinical.controller;

import lombok.AllArgsConstructor;
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;
import vn.derma.clinical.common.ApiResponse;
import vn.derma.clinical.dto.ClinicalDtos.ApplyTurnInput;
import vn.derma.clinical.dto.ClinicalDtos.HasData;
import vn.derma.clinical.dto.FinalizeDtos.CaseInput;
import vn.derma.clinical.service.ClinicalRecordService;
import vn.derma.clinical.service.FinalizeReportService;

/** Chỉ cho service khác (interceptor kiểm `X-Internal-Key`), không qua gateway. Danh sách ở services/contracts/README.md mục 3. */
@RestController
@RequestMapping("/internal")
@AllArgsConstructor
public class InternalController {

    private final ClinicalRecordService records;
    private final FinalizeReportService finalizeReports;

    /** knowledge đọc từng trang báo cáo đã chốt để reindex ca tham khảo (page bắt đầu từ 1). */
    @GetMapping("/finalize-reports")
    ApiResponse<List<CaseInput>> listFinalizeReports(@RequestParam(defaultValue = "1") int page, @RequestParam(name = "page_size", defaultValue = "50") int pageSize) {
        return new ApiResponse<>(finalizeReports.listCases(page, Math.min(Math.max(pageSize, 1), 200)));
    }

    /** ai ghi giả thuyết và dự đoán ảnh của lượt (fact nay ghi vào graph theo dõi ở knowledge). */
    @PostMapping("/episodes/apply-turn")
    ApiResponse<Void> applyTurn(@Valid @RequestBody ApplyTurnInput body) {
        records.applyClinicalEpisodeByTurn(body);
        return new ApiResponse<>(null);
    }

    /** identity hỏi trước khi xoá hồ sơ: đã có báo cáo kết luận chưa. */
    @GetMapping("/patients/{profileId}/has-data")
    ApiResponse<HasData> hasData(@PathVariable String profileId) {
        return new ApiResponse<>(new HasData(records.hasLinkedData(profileId)));
    }
}

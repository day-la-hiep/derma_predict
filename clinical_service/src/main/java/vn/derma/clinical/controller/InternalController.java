package vn.derma.clinical.controller;

import lombok.AllArgsConstructor;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;
import vn.derma.clinical.common.ApiResponse;
import vn.derma.clinical.dto.ClinicalDtos.ApplyTurnInput;
import vn.derma.clinical.dto.ClinicalDtos.HasData;
import vn.derma.clinical.dto.ClinicalDtos.PatientContext;
import vn.derma.clinical.dto.ClinicalDtos.ProfileFactOutput;
import vn.derma.clinical.dto.ClinicalDtos.ReplaceLongTermFactsInput;
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

    /** ai kéo fact hiện trạng của hồ sơ. */
    @GetMapping("/patients/{profileId}/context")
    ApiResponse<PatientContext> getContext(@PathVariable String profileId) {
        return new ApiResponse<>(records.getContext(profileId));
    }

    /** ai ghi kết quả lâm sàng của lượt (fact, giả thuyết, dự đoán ảnh). */
    @PostMapping("/episodes/apply-turn")
    ApiResponse<Void> applyTurn(@Valid @RequestBody ApplyTurnInput body) {
        records.applyTurn(body);
        return new ApiResponse<>(null);
    }

    /** identity ghép fact dài hạn vào danh sách hồ sơ. */
    @GetMapping("/patients/long-term-facts")
    ApiResponse<Map<String, List<ProfileFactOutput>>> getLongTermFacts(@RequestParam("profile_ids") String profileIds) {
        return new ApiResponse<>(records.getLongTermFacts(Arrays.stream(profileIds.split(",")).map(String::trim).filter(x -> !x.isEmpty()).toList()));
    }

    /** identity thay toàn bộ fact dài hạn từ form hồ sơ. */
    @PutMapping("/patients/{profileId}/long-term-facts")
    ApiResponse<List<ProfileFactOutput>> replaceLongTermFacts(@PathVariable String profileId, @Valid @RequestBody ReplaceLongTermFactsInput body) {
        return new ApiResponse<>(records.replaceLongTermFacts(profileId, body.facts()));
    }

    /** identity hỏi trước khi xoá hồ sơ: đã có báo cáo kết luận chưa. */
    @GetMapping("/patients/{profileId}/has-data")
    ApiResponse<HasData> hasData(@PathVariable String profileId) {
        return new ApiResponse<>(new HasData(records.hasLinkedData(profileId)));
    }
}

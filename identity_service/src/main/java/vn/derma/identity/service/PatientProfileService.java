package vn.derma.identity.service;

import lombok.AllArgsConstructor;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import vn.derma.identity.client.ClinicalClient;
import vn.derma.identity.client.ConsultationClient;
import vn.derma.identity.common.AppException;
import vn.derma.identity.dto.PatientProfileDtos.CreatePatientProfileInput;
import vn.derma.identity.dto.PatientProfileDtos.PatientProfileOutput;
import vn.derma.identity.dto.PatientProfileDtos.ProfileFactOutput;
import vn.derma.identity.dto.PatientProfileDtos.UpdatePatientProfileInput;
import vn.derma.identity.dto.ProfileRelationship;
import vn.derma.identity.entity.PatientProfile;
import vn.derma.identity.mapper.IdentityMapper;
import vn.derma.identity.repository.PatientProfileRepository;

@Service
@AllArgsConstructor
public class PatientProfileService {

    private static final int MAX_PHONE_LENGTH = 32;

    private final PatientProfileRepository profiles;
    private final ClinicalClient clinical;
    private final ConsultationClient consultation;
    private final IdentityMapper mapper;

    public List<PatientProfileOutput> list(String userId) {
        List<PatientProfile> mine = profiles.findByUserIdOrderByCreatedAtAsc(userId);
        Map<String, List<ProfileFactOutput>> facts = clinical.getLongTermFacts(mine.stream().map(p -> p.id).toList());
        return mine.stream().map(p -> mapper.toOutput(p, facts.getOrDefault(p.id, List.of()))).toList();
    }

    @Transactional
    public PatientProfileOutput create(String userId, CreatePatientProfileInput input) {
        PatientProfile profile = new PatientProfile();
        profile.userId = userId;
        profile.fullName = input.fullName();
        profile.dob = input.dob();
        profile.gender = input.gender().value();
        profile.relationship = (input.relationship() == null ? ProfileRelationship.SELF : input.relationship()).value();
        profile.phone = input.phone();
        profiles.save(profile);
        List<ProfileFactOutput> facts = input.longTermFacts() == null || input.longTermFacts().isEmpty()
                ? List.of()
                : clinical.replaceLongTermFacts(profile.id, input.longTermFacts());
        return mapper.toOutput(profile, facts);
    }

    @Transactional
    public PatientProfileOutput update(String userId, String profileId, UpdatePatientProfileInput input) {
        PatientProfile profile = getOwned(userId, profileId);
        if (input.fullName != null) {
            profile.fullName = input.fullName;
        }
        if (input.dob != null) {
            profile.dob = input.dob;
        }
        if (input.gender != null) {
            profile.gender = input.gender.value();
        }
        if (input.relationship != null) {
            profile.relationship = input.relationship.value();
        }
        if (input.phoneProvided()) {
            profile.phone = input.phone() == null ? null : checkPhone(input.phone());
        }
        List<ProfileFactOutput> facts = input.longTermFacts != null
                ? clinical.replaceLongTermFacts(profileId, input.longTermFacts)
                : clinical.getLongTermFacts(List.of(profileId)).getOrDefault(profileId, List.of());
        return mapper.toOutput(profile, facts);
    }

    @Transactional
    public void delete(String userId, String profileId) {
        PatientProfile profile = getOwned(userId, profileId);
        if (profiles.countByUserId(userId) <= 1) {
            throw AppException.conflict("Không thể xoá hồ sơ cuối cùng của tài khoản.");
        }
        if (consultation.hasPatientData(profileId) || clinical.hasPatientData(profileId)) {
            throw AppException.conflict("Hồ sơ đã có hội thoại hoặc báo cáo kết luận nên không thể xoá.");
        }
        profiles.delete(profile);
    }

    /** Dùng cho `/internal`: hồ sơ `profileId` của `userId`, hoặc hồ sơ đầu tiên của tài khoản khi `profileId` null. */
    public Optional<PatientProfile> resolveOwned(String userId, String profileId) {
        return profileId == null
                ? profiles.findByUserIdOrderByCreatedAtAsc(userId).stream().findFirst()
                : profiles.findByIdAndUserId(profileId, userId);
    }

    private Optional<PatientProfile> findOwned(String userId, String profileId) {
        return profiles.findByIdAndUserId(profileId, userId);
    }

    private PatientProfile getOwned(String userId, String profileId) {
        return findOwned(userId, profileId).orElseThrow(() -> AppException.notFound("hồ sơ bệnh nhân"));
    }

    private String checkPhone(String phone) {
        if (phone.length() > MAX_PHONE_LENGTH) {
            throw AppException.invalid("phone: tối đa " + MAX_PHONE_LENGTH + " ký tự");
        }
        return phone;
    }
}

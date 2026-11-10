package vn.derma.identity.mapper;

import java.util.List;

import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

import vn.derma.identity.controller.InternalController.ProfileDetail;
import vn.derma.identity.controller.InternalController.ProfileRef;
import vn.derma.identity.controller.InternalController.UserRef;
import vn.derma.identity.dto.AuthDtos.UserSummaryOutput;
import vn.derma.identity.dto.Gender;
import vn.derma.identity.dto.PatientProfileDtos.PatientProfileOutput;
import vn.derma.identity.dto.PatientProfileDtos.ProfileFactOutput;
import vn.derma.identity.entity.PatientProfile;
import vn.derma.identity.entity.User;

/** Entity → DTO; MapStruct đọc thẳng field public của entity và record của DTO. */
@Mapper(imports = Gender.class)
public interface IdentityMapper {

    @Mapping(target = "gender", expression = "java(Gender.fromValue(user.gender))")
    @Mapping(target = "role", source = "role")
    UserSummaryOutput toSummary(User user, String role);

    @Mapping(target = "longTermFacts", source = "facts")
    PatientProfileOutput toOutput(PatientProfile profile, List<ProfileFactOutput> facts);

    ProfileDetail toProfileDetail(PatientProfile profile);

    ProfileRef toProfileRef(PatientProfile profile);

    @Mapping(target = "id", source = "user.id")
    @Mapping(target = "fullName", source = "user.fullName")
    @Mapping(target = "role", source = "role")
    UserRef toUserRef(User user, String role);

    default String toText(Object value) {
        return value == null ? null : value.toString();
    }
}

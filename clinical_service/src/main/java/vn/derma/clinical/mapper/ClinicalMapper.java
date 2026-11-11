package vn.derma.clinical.mapper;

import java.time.Instant;

import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

import vn.derma.clinical.dto.ClinicalDtos.ContextFact;
import vn.derma.clinical.dto.ClinicalDtos.ProfileFactOutput;
import vn.derma.clinical.entity.ClinicalFact;

@Mapper
public interface ClinicalMapper {

    ProfileFactOutput toProfileFact(ClinicalFact fact);

    @Mapping(target = "label", source = "fact.label")
    @Mapping(target = "factType", source = "fact.factType")
    @Mapping(target = "detail", source = "fact.detail")
    @Mapping(target = "bodySite", source = "bodySite", defaultValue = "")
    ContextFact toContextFact(ClinicalFact fact, String bodySite);

    default String toText(Instant value) {
        return value == null ? null : value.toString();
    }
}

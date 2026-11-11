package vn.derma.identity.dto;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum ProfileRelationship {
    SELF("self"), CHILD("child"), PARENT("parent"), SPOUSE("spouse"), OTHER("other");

    private final String value;

    ProfileRelationship(String value) {
        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }

    @JsonCreator
    public static ProfileRelationship fromValue(String value) {
        for (ProfileRelationship r : values()) {
            if (r.value.equals(value)) {
                return r;
            }
        }
        throw new IllegalArgumentException("Quan hệ không hợp lệ: " + value);
    }
}

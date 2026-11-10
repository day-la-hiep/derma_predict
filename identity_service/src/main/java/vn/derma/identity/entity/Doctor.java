package vn.derma.identity.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "doctors")
public class Doctor {

    @Id
    @Column(name = "user_id")
    public String userId;
    @Column(nullable = false)
    public String description;
}

package vn.derma.identity.repository;

import org.springframework.data.jpa.repository.JpaRepository;

import vn.derma.identity.entity.Doctor;

public interface DoctorRepository extends JpaRepository<Doctor, String> {
}

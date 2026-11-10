package vn.derma.clinical.repository;

import org.springframework.data.jpa.repository.JpaRepository;

import vn.derma.clinical.entity.Encounter;

public interface EncounterRepository extends JpaRepository<Encounter, String> {

    java.util.Optional<Encounter> findByAppointmentId(String appointmentId);

    java.util.List<Encounter> findByAppointmentIdIn(java.util.Collection<String> appointmentIds);
}

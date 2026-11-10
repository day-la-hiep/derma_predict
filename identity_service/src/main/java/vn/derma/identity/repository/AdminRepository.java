package vn.derma.identity.repository;

import org.springframework.data.jpa.repository.JpaRepository;

import vn.derma.identity.entity.Admin;

public interface AdminRepository extends JpaRepository<Admin, String> {
}

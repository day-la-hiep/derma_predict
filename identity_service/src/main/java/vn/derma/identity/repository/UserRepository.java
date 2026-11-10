package vn.derma.identity.repository;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import vn.derma.identity.entity.User;

public interface UserRepository extends JpaRepository<User, String> {

    Optional<User> findByUsername(String username);
}

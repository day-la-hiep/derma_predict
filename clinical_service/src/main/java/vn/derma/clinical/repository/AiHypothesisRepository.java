package vn.derma.clinical.repository;

import java.util.Collection;
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

import vn.derma.clinical.entity.AiHypothesis;

public interface AiHypothesisRepository extends JpaRepository<AiHypothesis, String> {

    List<AiHypothesis> findByEpisodeIdOrderByRankAsc(String episodeId);

    List<AiHypothesis> findByEpisodeIdInOrderByRankAsc(Collection<String> episodeIds);

    void deleteByEpisodeId(String episodeId);
}

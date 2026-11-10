# Image service clinical (Spring Boot). Build context là thư mục này:
#   docker build -f clinical_service/Dockerfile -t derma-clinical clinical_service
FROM eclipse-temurin:21-jdk AS build
WORKDIR /build
COPY .mvn .mvn
COPY mvnw pom.xml ./
RUN chmod +x mvnw && ./mvnw -q -B dependency:go-offline
COPY src src
RUN ./mvnw -q -B -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /build/target/clinical-*.jar app.jar
EXPOSE 3053
ENTRYPOINT ["java", "-jar", "app.jar"]

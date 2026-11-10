# Image service identity (Spring Boot). Build context là thư mục này:
#   docker build -f identity_service/Dockerfile -t derma-identity identity_service
FROM eclipse-temurin:21-jdk AS build
WORKDIR /build
COPY .mvn .mvn
COPY mvnw pom.xml ./
RUN chmod +x mvnw && ./mvnw -q -B dependency:go-offline
COPY src src
RUN ./mvnw -q -B -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /build/target/identity-*.jar app.jar
EXPOSE 3051
ENTRYPOINT ["java", "-jar", "app.jar"]

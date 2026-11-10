# Image service gateway (Spring Boot). Build context là thư mục này:
#   docker build -f gateway_service/Dockerfile -t derma-gateway gateway_service
FROM eclipse-temurin:21-jdk AS build
WORKDIR /build
COPY .mvn .mvn
COPY mvnw pom.xml ./
RUN chmod +x mvnw && ./mvnw -q -B dependency:go-offline
COPY src src
RUN ./mvnw -q -B -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /build/target/gateway-*.jar app.jar
EXPOSE 3040
ENTRYPOINT ["java", "-jar", "app.jar"]

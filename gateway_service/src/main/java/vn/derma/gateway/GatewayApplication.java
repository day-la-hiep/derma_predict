package vn.derma.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** Cổng vào duy nhất cho FE: chỉ định tuyến theo đường dẫn, không verify JWT (mỗi service tự verify). Route nằm trong application.yml. */
@SpringBootApplication
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}

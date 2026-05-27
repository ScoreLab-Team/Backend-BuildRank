import http from "k6/http";
import { check, sleep } from "k6";

http.setResponseCallback(
  http.expectedStatuses(
    { min: 200, max: 399 },
    401,
    403,
    404
  )
);

export const options = {
  vus: 5,
  duration: "30s",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500"],
    checks: ["rate>0.95"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://host.docker.internal";

const endpoints = [
  "/api/accounts/me/",
  "/api/buildings/edificis/",
  "/api/seasons/",
  "/api/leagues/",
];

const params = {
  headers: {
    Host: "localhost",
    Accept: "application/json",
  },
};

export default function () {
  for (const path of endpoints) {
    const res = http.get(`${BASE_URL}${path}`, params);

    check(res, {
      [`${path} returns expected protected response`]: (r) =>
        r.status === 401 || r.status === 403,
      [`${path} does not return 5xx`]: (r) => r.status < 500,
      [`${path} response time < 500ms`]: (r) => r.timings.duration < 500,
    });
  }

  sleep(1);
}

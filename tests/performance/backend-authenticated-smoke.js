import http from "k6/http";
import { check, sleep } from "k6";

http.setResponseCallback(
  http.expectedStatuses(
    { min: 200, max: 399 },
    403,
    404
  )
);

export const options = {
  vus: 1,
  duration: "30s",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<800"],
    checks: ["rate>0.95"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://host.docker.internal";
const EMAIL = __ENV.K6_EMAIL || "k6.performance@buildrank.local";
const PASSWORD = __ENV.K6_PASSWORD || "K6Performance123";

const baseHeaders = {
  Host: "localhost",
  Accept: "application/json",
};

export function setup() {
  const loginRes = http.post(
    `${BASE_URL}/api/accounts/login/`,
    JSON.stringify({
      email: EMAIL,
      password: PASSWORD,
    }),
    {
      headers: {
        ...baseHeaders,
        "Content-Type": "application/json",
      },
      tags: { endpoint: "/api/accounts/login/" },
    }
  );

  const loginOk = check(loginRes, {
    "login returns 200": (r) => r.status === 200,
    "login returns access token": (r) => {
      try {
        return Boolean(r.json("access"));
      } catch (e) {
        return false;
      }
    },
  });

  if (!loginOk) {
    throw new Error(`Login failed. status=${loginRes.status} body=${loginRes.body}`);
  }

  return {
    token: loginRes.json("access"),
  };
}

const endpoints = [
  "/api/accounts/me/",
  "/api/accounts/me/edificis/",
  "/api/buildings/edificis/",
  "/api/seasons/",
  "/api/leagues/",
];

export default function (data) {
  const authParams = {
    headers: {
      ...baseHeaders,
      Authorization: `Bearer ${data.token}`,
    },
  };

  for (const path of endpoints) {
    const res = http.get(`${BASE_URL}${path}`, {
      ...authParams,
      tags: { endpoint: path },
    });

    check(res, {
      [`${path} returns 200/403/404`]: (r) =>
        r.status === 200 || r.status === 403 || r.status === 404,
      [`${path} does not return 401`]: (r) => r.status !== 401,
      [`${path} does not return 5xx`]: (r) => r.status < 500,
      [`${path} response time < 800ms`]: (r) => r.timings.duration < 800,
    });
  }

  sleep(1);
}

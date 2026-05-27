import http from "k6/http";

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
    }
  );

  console.log(`LOGIN status=${loginRes.status}`);
  console.log(loginRes.body.substring(0, 300));

  return {
    token: loginRes.json("access"),
  };
}

const endpoints = [
  "/api/accounts/me/",
  "/api/accounts/me/role/",
  "/api/accounts/me/edificis/",
  "/api/buildings/edificis/",
  "/api/seasons/",
  "/api/leagues/",
];

export default function (data) {
  for (const path of endpoints) {
    const res = http.get(`${BASE_URL}${path}`, {
      headers: {
        ...baseHeaders,
        Authorization: `Bearer ${data.token}`,
      },
    });

    console.log(`${path} status=${res.status} body=${res.body.substring(0, 250)}`);
  }
}

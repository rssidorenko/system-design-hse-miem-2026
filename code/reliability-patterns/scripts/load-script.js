import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

const SuccessRequests = new Counter('successful_requests');
const RateLimitedRequests = new Counter('rate_limited_requests');

export const options = {
  scenarios: {
    flood_attack: {
      executor: 'constant-vus',
      vus: 100,
      duration: '100s',
    },
  },

  thresholds: {
    'http_req_duration': ['p(95)<500'], 
  },
};

export default function () {
  const res = http.get('http://localhost:8080/ratelimit');

  const is200 = check(res, {
    'Status is 200 (OK)': (r) => r.status === 200,
  });

  const is429 = check(res, {
    'Status is 429 (Too Many Requests)': (r) => r.status === 429,
  });

  if (res.status === 200) {
    SuccessRequests.add(1);
  } else if (res.status === 429) {
    RateLimitedRequests.add(1);
  }

  sleep(0.1); 
}
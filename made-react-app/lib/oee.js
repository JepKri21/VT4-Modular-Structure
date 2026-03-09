// lib/oee.js
export const calculateOEE = (logs, idealCycleSec) => {
  const totalTime = logs.reduce(
    (sum, l) => sum + (new Date(l.end_time) - new Date(l.start_time)) / 1000,
    0,
  );
  const productiveTime = logs
    .filter((l) => l.status === "COMPLETE")
    .reduce(
      (sum, l) => sum + (new Date(l.end_time) - new Date(l.start_time)) / 1000,
      0,
    );
  const totalGood = logs.reduce((sum, l) => sum + l.good_count, 0);
  const totalProduced = logs.reduce(
    (sum, l) => sum + (l.good_count + l.reject_count),
    0,
  );

  const A = productiveTime / totalTime || 0;
  const P = productiveTime
    ? (totalProduced * idealCycleSec) / productiveTime
    : 0;
  const Q = totalProduced ? totalGood / totalProduced : 0;

  const OEE = A * P * Q;
  return { A, P, Q, OEE };
};

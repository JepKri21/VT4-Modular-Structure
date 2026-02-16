import React from "react";
import Hello from "../components/hello";

const Home = () => {
  console.log("Where is this posted?");

  return (
    <main>
      <div className="flex h-screen w-full items-center justify-center bg-primary">
        <h1 className="text-3xl font-bold text-primary">Welcome! 👋🏻</h1>
        <Hello />
      </div>
    </main>
  );
};

export default Home;

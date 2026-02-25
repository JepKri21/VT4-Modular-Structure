async function Page() {
  const response = await fetch("http://localhost:3001/api/books");
  const books = await response.json();

  return (
    <main>
      <code>{JSON.stringify(response, null, 2)}</code>
    </main>
  );
}

export default Page;

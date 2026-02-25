import books from "@/app/api/db";

export async function GET() {
  return Response.json({ books });
}

export async function POST(request: Request) {
  const book = await request.json();
  books.push(book);
  return Response.json({ message: "Book added successfully", books });
}

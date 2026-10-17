
// src/app/api/users/[userId]/route.ts
import { NextResponse } from 'next/server';
import { getDb, parseUserJSONFields } from '@/lib/server/database';
import type { User } from '@/types';
// import bcrypt from 'bcryptjs';

interface Params {
  params: { userId: string };
}

export async function GET(request: Request, { params }: Params) {
  try {
    const db = await getDb();
    const userRaw = await db.get('SELECT id, username, role, permissions, activeBreakId FROM users WHERE id = ?', params.userId);
    if (!userRaw) {
      return NextResponse.json({ message: 'User not found' }, { status: 404 });
    }
    const user = parseUserJSONFields(userRaw);
    return NextResponse.json(user);
  } catch (error) {
    console.error(`Failed to fetch user ${params.userId}:`, error);
    return NextResponse.json({ message: 'Failed to fetch user' }, { status: 500 });
  }
}

export async function PUT(request: Request, { params }: Params) {
  let db;
  let userDataFromRequest: Partial<User> = {}; // To hold parsed data for error messages

  try {
    try {
      userDataFromRequest = await request.json();
    } catch (e: unknown) {
      let parseErrorMessage = "Invalid JSON in request body for user update.";
      if (e instanceof SyntaxError) {
        parseErrorMessage = `Invalid JSON in request body for user update: ${e.message}`;
      } else if (e instanceof Error) {
        parseErrorMessage = `Error parsing JSON from request body for user update: ${e.message}`;
      }
      console.error(`Failed to parse request JSON body in PUT /api/users/${params.userId}:`, e);
      return NextResponse.json({ message: parseErrorMessage }, { status: 400 });
    }
    
    db = await getDb();
    const { userId } = params;

    if (userDataFromRequest.id && userDataFromRequest.id !== userId) {
      return NextResponse.json({ message: 'User ID mismatch in request body and URL path.' }, { status: 400 });
    }
    if (!userDataFromRequest.username || !userDataFromRequest.role) {
        return NextResponse.json({ message: 'Missing required user fields (username, role)' }, { status: 400 });
    }
     if (userDataFromRequest.password && userDataFromRequest.password.trim().length > 0 && userDataFromRequest.password.trim().length < 6) {
        return NextResponse.json({ message: 'New password must be at least 6 characters if provided' }, { status: 400 });
    }

    await db.run('BEGIN TRANSACTION');

    const existingUser = await db.get<User>('SELECT * FROM users WHERE id = ?', userId);
    if (!existingUser) {
         await db.run('ROLLBACK');
         return NextResponse.json({ message: 'User not found' }, { status: 404 });
    }

    let passwordToStore = existingUser.password;
    if (userDataFromRequest.password && userDataFromRequest.password.trim() !== "") {
      // passwordToStore = await bcrypt.hash(userData.password, 10); // Hash new password
      passwordToStore = userDataFromRequest.password.trim(); // Demo: direct password
    }

    const permissionsToStore = userDataFromRequest.role === 'manager' ? JSON.stringify(userDataFromRequest.permissions || []) : JSON.stringify([]);
    const autoEnterScanValue = userDataFromRequest.autoEnterAfterScan === undefined ? existingUser.autoEnterAfterScan : userDataFromRequest.autoEnterAfterScan;

    const result = await db.run(
      'UPDATE users SET username = ?, role = ?, permissions = ?, password = ?, activeBreakId = ?, auto_enter_after_scan = ? WHERE id = ?',
      userDataFromRequest.username,
      userDataFromRequest.role,
      permissionsToStore,
      passwordToStore,
      userDataFromRequest.activeBreakId === undefined ? existingUser.activeBreakId : userDataFromRequest.activeBreakId, // Keep existing if not provided
      autoEnterScanValue === false ? 0 : 1, // Store as integer
      userId
    );

    if (result.changes === 0) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: 'User not found or no changes made' }, { status: 404 });
    }
    
    await db.run('COMMIT');
    
    const updatedUserRaw = await db.get('SELECT id, username, role, permissions, activeBreakId, auto_enter_after_scan FROM users WHERE id = ?', userId);
    const updatedUser = parseUserJSONFields(updatedUserRaw);
    return NextResponse.json(updatedUser);

  } catch (error: any) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed in PUT user:", e));
    
    console.error(`Failed to update user ${params.userId}:`, error);
    let clientErrorMessage = `Failed to update user ${userDataFromRequest.username || params.userId}.`;
    let statusCode = 500;

    if (error && typeof error.message === 'string') {
     if (error.message.includes('UNIQUE constraint failed: users.username')) {
      clientErrorMessage = `Username "${userDataFromRequest.username}" already exists.`;
      statusCode = 409; // Conflict
     } else {
      clientErrorMessage = `Failed to update user: ${error.message}`;
     }
    }
    return NextResponse.json({ message: clientErrorMessage }, { status: statusCode });
  }
}

export async function DELETE(request: Request, { params }: Params) {
  try {
    const db = await getDb();
    // Consider adding checks: e.g., cannot delete the last admin user.
    const result = await db.run('DELETE FROM users WHERE id = ?', params.userId);
    if (result.changes === 0) {
      return NextResponse.json({ message: 'User not found' }, { status: 404 });
    }
    return NextResponse.json({ message: 'User deleted successfully' }, { status: 200 });
  } catch (error) {
    console.error(`Failed to delete user ${params.userId}:`, error);
    return NextResponse.json({ message: 'Failed to delete user' }, { status: 500 });
  }
}
